"""
Scraper Statbunker — complément de stats détaillées + validation croisée.

Rôle dans le pipeline :
  - Fournir les stats non disponibles sur LNR sans login :
    carries, meters, passes, kick_meters, errors, penalties_conceded,
    tackle_success_pct (total tackles), ruck_arrivals, lineout_wins, scrum_pct
  - Croiser avec les stats LNR pour détecter des anomalies

URL : https://www.statbunker.com/competitions/TopList?comp_id={id}

IDs Top14 connus :
  2023-2024 : comp_id=133
  2024-2025 : comp_id=154  (à confirmer)
  2025-2026 : comp_id=175  (à confirmer)

Usage :
    python scraper_statbunker.py --season 2023-2024 --output ../raw/statbunker_raw.json
    python scraper_statbunker.py --season 2023-2024 --lnr ../raw/lnr_raw.json --merge
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from http_client import RobustSession

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.statbunker.com"

# IDs competition Top14 (vérifier chaque saison sur statbunker.com/competitions)
COMP_IDS = {
    "2025-2026": 175,
    "2024-2025": 154,
    "2023-2024": 133,
    "2022-2023": 118,
    "2021-2022": 105,
}

# Types de stats disponibles
STAT_TYPES = {
    "tackles": {
        "cols": ["Tackles", "Missed Tackles", "Tackle %"],
        "maps": {
            "Tackles": "tackles_total",
            "Missed Tackles": "missed_tackles",
            "Tackle %": "tackle_success_pct",
        },
    },
    "carries": {
        "cols": ["Carries", "Metres", "Line Breaks", "Offloads"],
        "maps": {
            "Carries": "carries_total",
            "Metres": "meters_total",
            "Line Breaks": "line_breaks_total",
            "Offloads": "offloads_total",
        },
    },
    "passes": {
        "cols": ["Passes"],
        "maps": {"Passes": "passes_total"},
    },
    "kicking": {
        "cols": ["Kick Metres", "Points"],
        "maps": {
            "Kick Metres": "kick_meters_total",
            "Points": "points_scored_total_sb",  # Prefixe _sb pour éviter conflit
        },
    },
    "discipline": {
        "cols": ["Penalties", "Yellow Cards", "Red Cards"],
        "maps": {
            "Penalties": "penalties_total",
            "Yellow Cards": "yellow_cards_sb",
            "Red Cards": "red_cards_sb",
        },
    },
    "lineout": {
        "cols": ["Lineout Wins", "Lineout Lost"],
        "maps": {
            "Lineout Wins": "lineout_wins_total",
            "Lineout Lost": "lineout_lost_total",
        },
    },
    "scrum": {
        "cols": ["Scrum %"],
        "maps": {"Scrum %": "scrum_success_pct"},
    },
    "breakdown": {
        "cols": ["Turnovers Won", "Ruck Arrivals"],
        "maps": {
            "Turnovers Won": "turnovers_won_total_sb",
            "Ruck Arrivals": "ruck_arrivals_total",
        },
    },
}

# Positions Statbunker → groupe interne (Mode Groupes LNR)
POSITION_MAP_SB = {
    "Loosehead Prop": "FRONT_ROW",
    "Tighthead Prop": "FRONT_ROW",
    "Prop": "FRONT_ROW",
    "Hooker": "FRONT_ROW",
    "Lock": "LOCK",
    "Blindside Flanker": "BACK_ROW",
    "Openside Flanker": "BACK_ROW",
    "Flanker": "BACK_ROW",
    "Number 8": "BACK_ROW",
    "Scrum-half": "SCRUM_HALF",
    "Fly-half": "FLY_HALF",
    "Wing": "WINGER",
    "Centre": "CENTRE",
    "Full-back": "FULLBACK",
}

# Normalisation équipes Statbunker
TEAM_CANONICAL_SB = {
    "Toulouse": "Toulouse",
    "Stade Toulousain": "Toulouse",
    "Racing 92": "Racing 92",
    "La Rochelle": "La Rochelle",
    "Stade Rochelais": "La Rochelle",
    "Clermont": "Clermont",
    "ASM Clermont": "Clermont",
    "Bordeaux Begles": "Bordeaux",
    "Bordeaux-Begles": "Bordeaux",
    "UBB": "Bordeaux",
    "Castres": "Castres",
    "CO Castres": "Castres",
    "Montpellier": "Montpellier",
    "MHR": "Montpellier",
    "Lyon": "Lyon",
    "LOU": "Lyon",
    "Brive": "Brive",
    "Perpignan": "Perpignan",
    "USAP": "Perpignan",
    "Pau": "Pau",
    "Section Paloise": "Pau",
    "Vannes": "Vannes",
    "Toulon": "Toulon",
    "RC Toulon": "Toulon",
    "Stade Francais": "Paris",
    "Paris": "Paris",
    "Bayonne": "Bayonne",
    "Aviron Bayonnais": "Bayonne",
    "Montauban": "Montauban",
}


# ---------------------------------------------------------------------------
# Parsing HTML Statbunker
# ---------------------------------------------------------------------------

def _to_float(val) -> float | None:
    if val is None or str(val).strip() in ("", "-", "N/A"):
        return None
    try:
        return float(str(val).replace(",", ".").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _normalize_team_sb(raw: str) -> str:
    clean = raw.strip()
    return TEAM_CANONICAL_SB.get(clean, clean)


def parse_statbunker_table(html: str, stat_type: str) -> list[dict]:
    """Parse un tableau Statbunker et retourne une liste de dicts joueurs."""
    soup = BeautifulSoup(html, "lxml")
    column_map = STAT_TYPES[stat_type]["maps"]

    # Statbunker utilise des tableaux standard
    table = (
        soup.find("table", id=lambda i: i and "stat" in i.lower())
        or soup.find("table", class_=lambda c: c and "stat" in str(c).lower())
        or soup.find("table")
    )
    if not table:
        return []

    # Headers
    headers_raw = [th.get_text(strip=True) for th in table.find_all("th")]
    headers = [column_map.get(h, h) for h in headers_raw]

    rows = []
    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        row = {
            headers[i] if i < len(headers) else f"col_{i}": cell.get_text(strip=True)
            for i, cell in enumerate(cells)
        }
        # Extraire Player, Team, Position des premières colonnes
        if "Player" in row:
            row["name"] = row.pop("Player", "").strip()
        if "Team" in row:
            row["team"] = _normalize_team_sb(row.pop("Team", ""))
        if "Position" in row:
            pos_raw = row.pop("Position", "")
            row["position_raw"] = pos_raw
            row["position_group"] = POSITION_MAP_SB.get(pos_raw, "UNKNOWN")
        row["_stat_type"] = stat_type
        rows.append(row)

    return rows


def _player_key_sb(name: str) -> str:
    """Clé de normalisation pour matcher avec LNR."""
    return re.sub(r"[^a-z]", "", name.lower())


# ---------------------------------------------------------------------------
# Scraping principal
# ---------------------------------------------------------------------------

def scrape_all_stats(session: RobustSession, season: str) -> list[dict]:
    """
    Scrape toutes les catégories de stats Statbunker.
    Retourne une liste de joueurs avec toutes les stats disponibles.
    """
    comp_id = COMP_IDS.get(season)
    if not comp_id:
        session.logger.warning(
            f"Pas d'ID Statbunker pour saison {season}. "
            f"IDs connus : {list(COMP_IDS.keys())}"
        )
        return []

    print(f"\n[Statbunker] Saison {season} (comp_id={comp_id})")
    all_rows = []

    for stat_type in STAT_TYPES:
        url = f"{BASE_URL}/competitions/TopList"
        params = {"comp_id": comp_id, "type": stat_type, "limit": 500}
        print(f"  -> {stat_type}")

        html = session.get(url, params=params, snapshot_name=f"sb_{stat_type}_{season}")
        if not html:
            print(f"     ECHEC")
            continue

        rows = parse_statbunker_table(html, stat_type)
        print(f"     {len(rows)} joueurs")
        all_rows.extend(rows)

    # Déduplication : un joueur par ligne, fusionner les stats
    players: dict[str, dict] = {}
    for row in all_rows:
        name = row.get("name", "").strip()
        if not name:
            continue
        key = _player_key_sb(name)
        if key not in players:
            players[key] = {
                "name": name,
                "name_key": key,
                "team": row.get("team", ""),
                "position_raw": row.get("position_raw", ""),
                "position_group": row.get("position_group", "UNKNOWN"),
                "_source": "statbunker",
            }
        for k, v in row.items():
            if k not in ("name", "team", "_stat_type") and k not in players[key]:
                players[key][k] = v

    result = list(players.values())
    print(f"\n[Statbunker] {len(result)} joueurs uniques collectés")
    return result


def compute_per80_sb(players: list[dict]) -> list[dict]:
    """Calcule les stats /80 min pour les données Statbunker."""
    for p in players:
        mins = _to_float(p.get("Minutes") or p.get("minutes_total"))
        if not mins or mins <= 0:
            continue

        def per80(field: str) -> float | None:
            val = _to_float(p.get(field))
            return round(val / mins * 80, 2) if val is not None else None

        p["tackles_per80"] = per80("tackles_total")
        p["carries_per80"] = per80("carries_total")
        p["meters_per80"] = per80("meters_total")
        p["passes_per80"] = per80("passes_total")
        p["kick_meters_per80"] = per80("kick_meters_total")
        p["penalties_per80"] = per80("penalties_total")
        p["errors_per80"] = per80("errors_total")
        p["ruck_arrivals_per80"] = per80("ruck_arrivals_total")
        p["lineout_wins_per80"] = per80("lineout_wins_total")
        p["turnovers_lost_per80"] = per80("turnovers_lost_total")

    return players


# ---------------------------------------------------------------------------
# Fusion avec LNR
# ---------------------------------------------------------------------------

def merge_with_lnr(lnr_players: list[dict], sb_players: list[dict]) -> list[dict]:
    """
    Enrichit chaque joueur LNR avec les stats Statbunker manquantes.
    LNR = source authoritative pour l'identité et les stats disponibles.
    Statbunker complète uniquement les champs None.

    Stratégie de matching : normalisation du nom (sans accents, lowercase).
    """
    # Index Statbunker par clé nom
    sb_index: dict[str, dict] = {p["name_key"]: p for p in sb_players}

    # Stats à compléter depuis Statbunker
    sb_stats_to_fill = [
        "tackles_per80", "tackle_success_pct",
        "carries_per80", "meters_per80", "passes_per80",
        "kick_meters_per80", "penalties_per80", "errors_per80",
        "turnovers_lost_per80", "ruck_arrivals_per80",
        "lineout_wins_per80", "scrum_success_pct",
    ]

    # En mode Groupes LNR, FRONT_ROW/BACK_ROW sont les groupes larges utilisés
    # Statbunker peut raffiner, mais on reste sur ces groupes pour cohérence
    BROAD_POSITIONS = {"FRONT_ROW", "BACK_ROW"}

    matched, partial = 0, 0

    for player in lnr_players:
        # Clé de matching
        name = player.get("name", "")
        key = re.sub(r"[^a-z]", "", name.lower())

        sb = sb_index.get(key)
        if not sb:
            # Essai avec le nom partiel (nom de famille seulement)
            name_parts = name.lower().split()
            if len(name_parts) >= 2:
                last = re.sub(r"[^a-z]", "", name_parts[-1])
                for sb_key, sb_p in sb_index.items():
                    if last and last in sb_key and len(last) > 3:
                        sb = sb_p
                        break

        if sb:
            filled = []
            for field in sb_stats_to_fill:
                if player.get(field) is None and sb.get(field) is not None:
                    player[field] = sb[field]
                    filled.append(field)

            # Corriger les positions larges LNR avec les positions précises Statbunker
            sb_pos = sb.get("position_group", "")
            lnr_pos = player.get("position_group", "")
            if (
                lnr_pos in BROAD_POSITIONS
                and sb_pos not in ("", "UNKNOWN")
                and sb_pos != lnr_pos
            ):
                player["position_group"] = sb_pos
                player["position_raw_sb"] = sb.get("position_raw", "")
                filled.append("position_group")

            if filled:
                player["_source"] = "lnr+statbunker"
                player["_sb_fields"] = filled
                matched += 1 if len(filled) >= 3 else 0
                partial += 1 if len(filled) < 3 else 0

    print(
        f"[Merge LNR+Statbunker] {matched} joueurs enrichis (≥3 stats), "
        f"{partial} enrichissements partiels"
    )
    return lnr_players


# ---------------------------------------------------------------------------
# Validation croisée
# ---------------------------------------------------------------------------

def cross_validate(
    lnr_players: list[dict],
    sb_players: list[dict],
    tolerance: float = 0.20,
) -> list[dict]:
    """
    Détecte les divergences entre LNR et Statbunker sur les stats en commun.
    Retourne une liste d'anomalies triée par sévérité.
    """
    sb_index = {p["name_key"]: p for p in sb_players}

    # Stats présentes dans les deux sources
    fields_to_check = [
        ("offloads_per80", "offloads_per80"),
        ("line_breaks_per80", "line_breaks_per80"),
        ("turnovers_won_total", "turnovers_won_total_sb"),
        ("points_scored_total", "points_scored_total_sb"),
    ]

    anomalies = []
    for player in lnr_players:
        key = re.sub(r"[^a-z]", "", player.get("name", "").lower())
        sb = sb_index.get(key)
        if not sb:
            continue

        for lnr_field, sb_field in fields_to_check:
            lnr_val = _to_float(player.get(lnr_field))
            sb_val = _to_float(sb.get(sb_field))
            if lnr_val is None or sb_val is None or sb_val == 0:
                continue

            diff_pct = abs(lnr_val - sb_val) / max(abs(sb_val), 0.01)
            if diff_pct > tolerance:
                anomalies.append({
                    "name": player["name"],
                    "team": player["team"],
                    "field": lnr_field,
                    "lnr_value": lnr_val,
                    "statbunker_value": sb_val,
                    "diff_pct": round(diff_pct * 100, 1),
                    "severity": "HIGH" if diff_pct > 0.40 else "MEDIUM",
                })

    anomalies.sort(key=lambda x: (0 if x["severity"] == "HIGH" else 1, -x["diff_pct"]))
    high = sum(1 for a in anomalies if a["severity"] == "HIGH")
    print(f"[Validation croisée] {len(anomalies)} divergences ({high} HIGH, tolérance={tolerance:.0%})")
    return anomalies


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper Statbunker (complément + validation)")
    parser.add_argument("--season", default="2023-2024")
    parser.add_argument("--output", default="../raw/statbunker_raw.json")
    parser.add_argument("--lnr", default=None, help="Fichier LNR JSON à enrichir")
    parser.add_argument("--merge", action="store_true", help="Fusionner avec LNR")
    parser.add_argument("--merged-output", default="../raw/players_merged.json")
    parser.add_argument("--anomalies-output", default="../raw/cross_validation.json")
    args = parser.parse_args()

    session = RobustSession(source_name="Statbunker", request_delay=3.0)
    base = Path(__file__).parent
    output_path = (base / args.output).resolve()

    sb_players = scrape_all_stats(session, args.season)
    sb_players = compute_per80_sb(sb_players)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sb_players, f, ensure_ascii=False, indent=2)
    print(f"[OK] {len(sb_players)} joueurs -> {output_path}")

    if args.lnr and args.merge:
        lnr_path = (base / args.lnr).resolve()
        if lnr_path.exists():
            with open(lnr_path, encoding="utf-8") as f:
                lnr_players = json.load(f)

            # Validation croisée
            anomalies = cross_validate(lnr_players, sb_players)
            anom_path = (base / args.anomalies_output).resolve()
            with open(anom_path, "w", encoding="utf-8") as f:
                json.dump(anomalies, f, ensure_ascii=False, indent=2)
            print(f"[OK] Anomalies -> {anom_path}")

            # Fusion
            merged = merge_with_lnr(lnr_players, sb_players)
            merged_path = (base / args.merged_output).resolve()
            with open(merged_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            print(f"[OK] {len(merged)} joueurs fusionnés -> {merged_path}")

    print(f"\n[Statbunker] Session : {session.stats_summary()}")


if __name__ == "__main__":
    main()
