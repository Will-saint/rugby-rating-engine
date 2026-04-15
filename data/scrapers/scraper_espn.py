"""
Scraper ESPN Rugby — métriques avancées manquantes.

ESPN rugby expose une API JSON non documentée qui retourne les stats
per-player pour plusieurs compétitions. On cible :
  • Top 14 (league_id = 23)
  • Champions Cup (league_id = 272)

Métriques récupérées (non disponibles sur LNR public) :
  meters_gained, defenders_beaten, carries, passes,
  tackle_ratio_pct, offload_ratio_pct, turnovers_conceded,
  penalties_conceded, missed_tackles

Stratégie :
  1. ESPN summary stats endpoint (JSON) → parsing rapide
  2. Si absent : rugbypass.com fallback (HTML scraping)
  3. Matching avec notre base LNR via normalisation nom + poste

Usage :
    python scraper_espn.py --season 2025-2026 --output ../raw/espn_raw.json
    python scraper_espn.py --dry-run   (affiche les URLs sans scraper)

Sortie (JSON) :
    [
      {
        "espn_id": "...", "name": "...", "team": "...", "position_espn": "...",
        "meters_gained": 123.4, "defenders_beaten": 5.6,
        "carries": 7.8, "passes": 45.2,
        "tackle_ratio_pct": 87.3, "missed_tackles": 1.2,
        "turnovers_conceded": 0.8, "penalties_conceded": 1.1
      },
      ...
    ]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT_SCRAPER = Path(__file__).parent
ROOT = ROOT_SCRAPER.parent.parent
sys.path.insert(0, str(ROOT_SCRAPER))

try:
    from http_client import RobustSession
except ImportError:
    import requests

    class RobustSession:  # type: ignore[no-redef]
        """Fallback minimal si http_client absent."""
        def __init__(self, *_, **__):
            self._s = requests.Session()
            self._s.headers.update({
                "User-Agent": "Mozilla/5.0 (compatible; RugbyRatingBot/1.0)"
            })

        def get(self, url, **kwargs):
            kwargs.setdefault("timeout", 15)
            return self._s.get(url, **kwargs)

        def close(self):
            self._s.close()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ESPN_TOP14_ID     = 23     # ESPN league ID pour le Top 14
ESPN_CHAMP_CUP_ID = 272    # Champions Cup

ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports/rugby"

# Endpoint stats générales d'une compétition
ESPN_STATS_URL = (
    f"{ESPN_API_BASE}/{ESPN_TOP14_ID}/statistics"
    "?limit=500&season={year}&seasontype=2"
)

# Alternative : endpoint athletes d'une équipe (plus stable)
ESPN_TEAM_ROSTER = (
    f"{ESPN_API_BASE}/{ESPN_TOP14_ID}/teams/{{team_id}}/roster"
    "?season={year}"
)

# Rugbypass fallback (tableau HTML parseable)
RUGBYPASS_STATS_URL = (
    "https://www.rugbypass.com/super-rugby/stats/players/"
    "?competition=top-14&season={year}&stat=metres-gained"
)

# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def _norm_name(name: str) -> str:
    """Supprime accents, met en majuscules, retire ponctuation."""
    s = unicodedata.normalize("NFD", str(name).upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z\s]", " ", s)
    return " ".join(s.split())


def _match_name(espn_name: str, lnr_name: str, threshold: float = 0.65) -> bool:
    """Correspondance floue par tokens communs (pas de dépendance fuzzywuzzy)."""
    tokens_e = set(_norm_name(espn_name).split())
    tokens_l = set(_norm_name(lnr_name).split())
    if not tokens_e or not tokens_l:
        return False
    # Jaccard simplifié
    intersection = len(tokens_e & tokens_l)
    union        = len(tokens_e | tokens_l)
    return (intersection / union) >= threshold


# ---------------------------------------------------------------------------
# ESPN API scraper
# ---------------------------------------------------------------------------

def _fetch_espn_stats(year: int, session: RobustSession) -> list[dict]:
    """
    Récupère les statistiques ESPN pour le Top 14.
    Retourne une liste de dicts par joueur.
    """
    url = ESPN_STATS_URL.format(year=year)
    print(f"[ESPN] GET {url}")
    try:
        resp = session.get(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ESPN] Erreur réseau : {e}")
        return []

    try:
        data = resp.json()
    except Exception as e:
        print(f"[ESPN] Réponse non-JSON : {e}")
        return []

    # Parcourir la structure ESPN athletes/statistics
    players = []
    categories = data.get("categories", [])
    athletes   = data.get("athletes", [])

    # Format 1 : structure {athletes: [{athlete: {...}, statistics: [...]}]}
    if athletes and isinstance(athletes[0], dict) and "athlete" in athletes[0]:
        for entry in athletes:
            ath  = entry.get("athlete", {})
            stats_list = entry.get("statistics", [])
            row = _parse_espn_athlete(ath, stats_list, categories)
            if row:
                players.append(row)

    # Format 2 : structure plate avec indexes
    elif "rows" in data:
        for row_data in data["rows"]:
            row = _parse_espn_row(row_data)
            if row:
                players.append(row)

    print(f"[ESPN] {len(players)} joueurs parsés")
    return players


def _parse_espn_athlete(ath: dict, stats_list: list, categories: list) -> dict | None:
    """Parse un joueur depuis la structure ESPN athletes."""
    name = ath.get("displayName", ath.get("fullName", ""))
    if not name:
        return None

    team = ""
    team_data = ath.get("team", {})
    if isinstance(team_data, dict):
        team = team_data.get("displayName", "")

    position_espn = ""
    pos_data = ath.get("position", {})
    if isinstance(pos_data, dict):
        position_espn = pos_data.get("abbreviation", "")

    row = {
        "espn_id":        ath.get("id", ""),
        "name":           name,
        "team":           team,
        "position_espn":  position_espn,
        "meters_gained":  None,
        "defenders_beaten": None,
        "carries":        None,
        "passes":         None,
        "tackle_ratio_pct": None,
        "missed_tackles": None,
        "turnovers_conceded": None,
        "penalties_conceded": None,
    }

    # Mapping ESPN stat names → nos colonnes
    stat_map = {
        "metersgained":       "meters_gained",
        "metersrun":          "meters_gained",
        "defensorsbeaten":    "defenders_beaten",
        "defeatersbeaten":    "defenders_beaten",
        "carries":            "carries",
        "passes":             "passes",
        "tacklesmade":        None,          # brut — calculer ratio séparément
        "tacklesmissed":      "missed_tackles",
        "tacklesuccess":      "tackle_ratio_pct",
        "turnoversconceded":  "turnovers_conceded",
        "penaltiesconceded":  "penalties_conceded",
    }

    for i, stat_entry in enumerate(stats_list):
        cat_name = ""
        if i < len(categories):
            cat_name = str(categories[i].get("name", "")).lower().replace(" ", "")
        target = stat_map.get(cat_name)
        if target:
            try:
                row[target] = float(stat_entry.get("value", 0))
            except (TypeError, ValueError):
                pass

    return row


def _parse_espn_row(row_data: dict) -> dict | None:
    """Parse une ligne plate ESPN (format alternatif)."""
    name = row_data.get("name", "")
    if not name:
        return None
    return {
        "espn_id":          row_data.get("id", ""),
        "name":             name,
        "team":             row_data.get("team", ""),
        "position_espn":    row_data.get("position", ""),
        "meters_gained":    _safe_float(row_data.get("metersGained")),
        "defenders_beaten": _safe_float(row_data.get("defenderBeaten")),
        "carries":          _safe_float(row_data.get("carries")),
        "passes":           _safe_float(row_data.get("passes")),
        "tackle_ratio_pct": _safe_float(row_data.get("tackleSuccess")),
        "missed_tackles":   _safe_float(row_data.get("missedTackles")),
        "turnovers_conceded": _safe_float(row_data.get("turnoversConceded")),
        "penalties_conceded": _safe_float(row_data.get("penaltiesConceded")),
    }


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Rugbypass fallback (HTML)
# ---------------------------------------------------------------------------

def _fetch_rugbypass_stats(year: int, session: RobustSession) -> list[dict]:
    """
    Scrape rugbypass.com pour les stats avancées Top 14.
    Fallback si ESPN est indisponible.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[RUGBYPASS] BeautifulSoup non disponible — fallback ignoré.")
        return []

    url = RUGBYPASS_STATS_URL.format(year=year)
    print(f"[RUGBYPASS] GET {url}")
    try:
        resp = session.get(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"[RUGBYPASS] Erreur réseau : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Chercher le tableau de stats
    table = soup.find("table", class_=re.compile(r"stats|player", re.I))
    if not table:
        print("[RUGBYPASS] Tableau non trouvé — structure HTML peut avoir changé.")
        return []

    rows_data = []
    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]

    for tr in table.find_all("tr")[1:]:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        row = dict(zip(headers, tds))
        rows_data.append({
            "espn_id":          "",
            "name":             row.get("player", row.get("name", "")),
            "team":             row.get("club", row.get("team", "")),
            "position_espn":    row.get("pos", ""),
            "meters_gained":    _safe_float(row.get("metres gained", row.get("metres", None))),
            "defenders_beaten": _safe_float(row.get("defenders beaten", None)),
            "carries":          _safe_float(row.get("carries", None)),
            "passes":           _safe_float(row.get("passes", None)),
            "tackle_ratio_pct": _safe_float(row.get("tackle success %", None)),
            "missed_tackles":   _safe_float(row.get("missed tackles", None)),
            "turnovers_conceded": _safe_float(row.get("turnovers conceded", None)),
            "penalties_conceded": _safe_float(row.get("penalties conceded", None)),
        })

    print(f"[RUGBYPASS] {len(rows_data)} joueurs parsés")
    return rows_data


# ---------------------------------------------------------------------------
# Matching ESPN → LNR
# ---------------------------------------------------------------------------

def match_to_lnr(
    espn_players: list[dict],
    lnr_players: list[dict],
    verbose: bool = True,
) -> list[dict]:
    """
    Tente de matcher chaque joueur ESPN avec un joueur LNR.
    Ajoute lnr_slug + lnr_id aux enregistrements ESPN matchés.

    Args:
        espn_players : liste de dicts ESPN
        lnr_players  : liste de dicts LNR (depuis lnr_raw.json)

    Returns:
        Liste enrichie avec lnr_slug, lnr_id, matched (bool)
    """
    result = []
    matched_count = 0

    for ep in espn_players:
        best_match = None
        best_score = 0.0

        for lp in lnr_players:
            if _match_name(ep["name"], lp.get("name", "")):
                score = 1.0
                best_match = lp
                best_score = score
                break

        ep["lnr_slug"]  = best_match.get("lnr_slug", "") if best_match else ""
        ep["lnr_id"]    = best_match.get("lnr_id", None) if best_match else None
        ep["matched"]   = bool(best_match)
        if best_match:
            matched_count += 1
        result.append(ep)

    if verbose:
        print(f"[MATCH] {matched_count}/{len(espn_players)} joueurs ESPN matchés avec LNR")
    return result


# ---------------------------------------------------------------------------
# Merge avec players.csv
# ---------------------------------------------------------------------------

def enrich_lnr_with_espn(
    lnr_csv_path: str | Path,
    espn_data: list[dict],
    output_path: str | Path | None = None,
) -> "pd.DataFrame":
    """
    Fusionne les stats ESPN dans le CSV LNR existant.
    Colonnes ajoutées :
      meters_gained_espn, defenders_beaten_espn, carries_espn, passes_espn,
      tackle_ratio_espn, missed_tackles_espn, turnovers_conceded_espn, penalties_conceded_espn

    Si output_path fourni, sauvegarde le CSV enrichi.
    """
    import pandas as pd

    df = pd.read_csv(lnr_csv_path)

    espn_map = {e["lnr_slug"]: e for e in espn_data if e.get("matched") and e.get("lnr_slug")}

    espn_cols = [
        "meters_gained", "defenders_beaten", "carries", "passes",
        "tackle_ratio_pct", "missed_tackles", "turnovers_conceded", "penalties_conceded"
    ]
    for col in espn_cols:
        df[f"{col}_espn"] = None

    for idx, row in df.iterrows():
        slug = row.get("lnr_slug", "")
        if slug and slug in espn_map:
            espn_row = espn_map[slug]
            for col in espn_cols:
                v = espn_row.get(col)
                if v is not None:
                    df.at[idx, f"{col}_espn"] = v

    n_enriched = df[[f"{c}_espn" for c in espn_cols[:1]]].notna().sum().iloc[0]
    print(f"[ENRICH] {n_enriched} joueurs enrichis avec données ESPN")

    if output_path:
        df.to_csv(output_path, index=False)
        print(f"[ENRICH] Sauvegardé → {output_path}")

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scraper ESPN Rugby — métriques avancées Top 14")
    p.add_argument("--season", default="2025-2026",
                   help="Saison cible (ex: 2025-2026)")
    p.add_argument("--output", default=str(ROOT / "data" / "raw" / "espn_raw.json"),
                   help="Chemin de sortie JSON")
    p.add_argument("--lnr-csv", default=str(ROOT / "data" / "players.csv"),
                   help="CSV LNR source pour le matching")
    p.add_argument("--dry-run", action="store_true",
                   help="Affiche les URLs sans scraper")
    p.add_argument("--fallback-rugbypass", action="store_true",
                   help="Utilise rugbypass.com si ESPN échoue")
    p.add_argument("--enrich-csv", action="store_true",
                   help="Fusionne les données ESPN dans players.csv")
    return p


def main():
    args = _build_arg_parser().parse_args()

    year = int(args.season.split("-")[0])

    if args.dry_run:
        print("=== DRY RUN — URLs à scraper ===")
        print(f"ESPN Top 14 stats : {ESPN_STATS_URL.format(year=year)}")
        print(f"Rugbypass fallback : {RUGBYPASS_STATS_URL.format(year=year)}")
        return

    session = RobustSession()

    # 1. ESPN
    players = _fetch_espn_stats(year, session)

    # 2. Fallback rugbypass
    if (not players or all(p["meters_gained"] is None for p in players)) and args.fallback_rugbypass:
        print("[INFO] ESPN sans données utiles — tentative rugbypass fallback...")
        players = _fetch_rugbypass_stats(year, session)

    if not players:
        print("[WARN] Aucune donnée récupérée. Le site ESPN ou Rugbypass est peut-être :")
        print("       • Inaccessible depuis cet environnement")
        print("       • La structure HTML/JSON a changé")
        print("       → Mettre à jour les URLs et le parser manuellement.")
        session.close()
        return

    # 3. Matching avec LNR
    lnr_path = Path(args.lnr_csv)
    if lnr_path.exists():
        import pandas as pd
        df_lnr = pd.read_csv(lnr_path)
        lnr_list = df_lnr.to_dict("records")
        players = match_to_lnr(players, lnr_list)
    else:
        print(f"[WARN] {args.lnr_csv} non trouvé — matching ignoré.")
        for p in players:
            p["matched"] = False

    # 4. Sauvegarde JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] {len(players)} joueurs sauvegardés → {output_path}")

    # 5. Enrichissement CSV
    if args.enrich_csv and lnr_path.exists():
        enriched_path = ROOT / "data" / "players_espn_enriched.csv"
        enrich_lnr_with_espn(lnr_path, players, enriched_path)

    session.close()
    print("[DONE] ESPN scraper terminé.")


if __name__ == "__main__":
    main()
