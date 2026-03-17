"""
Extract Statbunker Positions — extrait position_fine depuis les données SB.

Objectif : obtenir HOOKER et NUMBER_8 pour affiner les groupes LNR
  (FRONT_ROW → PROP / HOOKER, BACK_ROW → FLANKER / NUMBER_8)

Sources (par ordre de préférence) :
  1. data/raw/statbunker_raw.json (déjà scrappé)
  2. data/raw/html_cache/sb_*.html (pages HTML en cache)

Matching sur (last_name, team) contre players.csv.
Exporte data/statbunker_positions.csv avec :
  player_id, name, team, position_fine, confidence_match

Usage :
    python data/scrapers/extract_sb_positions.py
    python data/scrapers/extract_sb_positions.py --input data/raw/statbunker_raw.json
    python data/scrapers/extract_sb_positions.py --output data/statbunker_positions.csv
    python data/scrapers/extract_sb_positions.py --report  # affiche stats de matching
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

# Positions fines reconnues par Statbunker
POSITION_FINE_MAP = {
    "Loosehead Prop":   "PROP",
    "Tighthead Prop":   "PROP",
    "Prop":             "PROP",
    "Hooker":           "HOOKER",
    "Lock":             "LOCK",
    "Blindside Flanker": "FLANKER",
    "Openside Flanker": "FLANKER",
    "Flanker":          "FLANKER",
    "Number 8":         "NUMBER_8",
    "Scrum-half":       "SCRUM_HALF",
    "Fly-half":         "FLY_HALF",
    "Wing":             "WINGER",
    "Centre":           "CENTRE",
    "Full-back":        "FULLBACK",
}

# Seulement les positions fines qui diffèrent des groupes LNR
FINE_POSITIONS_OF_INTEREST = {"PROP", "HOOKER", "FLANKER", "NUMBER_8"}


def normalize_name_key(name: str) -> str:
    """Clé de normalisation pour matching : lettres minuscules uniquement."""
    return re.sub(r"[^a-z]", "", name.lower())


def last_name_key(name: str) -> str:
    """Dernier mot du nom comme clé (ignore prénom)."""
    parts = name.strip().split()
    return normalize_name_key(parts[-1]) if parts else ""


def normalize_team(team: str) -> str:
    """Normalise le nom d'équipe pour matching."""
    # Extraire le premier mot significatif (ex: "Stade Toulousain" → "toulouse")
    TEAM_ALIASES = {
        "toulouse": "toulouse",
        "stade toulousain": "toulouse",
        "la rochelle": "la rochelle",
        "stade rochelais": "la rochelle",
        "bordeaux": "bordeaux",
        "bordeaux-begles": "bordeaux",
        "ubb": "bordeaux",
        "clermont": "clermont",
        "asm clermont": "clermont",
        "racing 92": "racing",
        "racing": "racing",
        "toulon": "toulon",
        "rc toulon": "toulon",
        "lyon": "lyon",
        "lou": "lyon",
        "montpellier": "montpellier",
        "mhr": "montpellier",
        "castres": "castres",
        "stade francais": "paris",
        "paris": "paris",
        "bayonne": "bayonne",
        "pau": "pau",
        "section paloise": "pau",
        "perpignan": "perpignan",
        "usap": "perpignan",
        "brive": "brive",
        "montauban": "montauban",
        "vannes": "vannes",
    }
    t = team.strip().lower()
    return TEAM_ALIASES.get(t, t.split()[0] if t else t)


def load_sb_data(sb_path: Path) -> list[dict]:
    """Charge les données Statbunker depuis statbunker_raw.json."""
    if not sb_path.exists():
        return []
    try:
        with open(sb_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return list(data.values())
    except Exception as e:
        print(f"[WARN] Erreur lecture {sb_path}: {e}")
    return []


def load_lnr_players(csv_path: Path) -> list[dict]:
    """Charge les joueurs LNR depuis players.csv."""
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        return df.to_dict("records")
    except Exception as e:
        print(f"[ERR] Erreur lecture {csv_path}: {e}")
        return []


def match_players(sb_players: list[dict], lnr_players: list[dict]) -> list[dict]:
    """
    Matching (last_name, team) entre joueurs SB et LNR.
    Retourne une liste de correspondances avec confidence_match.
    """
    # Index LNR : (last_name_key, team_normalized) → player_id
    lnr_index: dict[tuple, list] = {}
    for p in lnr_players:
        name = str(p.get("name", ""))
        team = str(p.get("team", ""))
        lk = last_name_key(name)
        tk = normalize_team(team)
        key = (lk, tk)
        lnr_index.setdefault(key, []).append(p)

    # Index LNR par last_name seul (fallback)
    lnr_by_lastname: dict[str, list] = {}
    for p in lnr_players:
        lk = last_name_key(str(p.get("name", "")))
        lnr_by_lastname.setdefault(lk, []).append(p)

    results = []
    for sb in sb_players:
        sb_name = str(sb.get("name", "")).strip()
        sb_team = str(sb.get("team", "")).strip()
        pos_raw = str(sb.get("position_raw", "")).strip()
        position_fine = POSITION_FINE_MAP.get(pos_raw)

        if not position_fine or not sb_name:
            continue

        lk = last_name_key(sb_name)
        tk = normalize_team(sb_team)

        # Stratégie 1 : last_name + team exact
        candidates = lnr_index.get((lk, tk), [])
        confidence = "exact" if candidates else None

        # Stratégie 2 : last_name seul (si équipe différente ou inconnue)
        if not candidates:
            candidates = lnr_by_lastname.get(lk, [])
            confidence = "last_name_only" if candidates else None

        if not candidates:
            continue

        # Prendre le premier candidat (ou celui avec le même groupe de poste)
        sb_pg = sb.get("position_group", "UNKNOWN")
        same_pg = [c for c in candidates if c.get("position_group") == sb_pg]
        best = same_pg[0] if same_pg else candidates[0]

        results.append({
            "player_id": str(best.get("player_id", "")),
            "name_lnr": str(best.get("name", "")),
            "name_sb": sb_name,
            "team": str(best.get("team", "")),
            "position_fine": position_fine,
            "position_raw_sb": pos_raw,
            "position_group_lnr": str(best.get("position_group", "")),
            "confidence_match": confidence,
        })

    return results


def export_csv(matches: list[dict], out_path: Path) -> None:
    """Exporte les correspondances en CSV."""
    try:
        import pandas as pd
        df = pd.DataFrame(matches)
        df = df.drop_duplicates(subset=["player_id"], keep="first")
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"[OK] {len(df)} joueurs exportés → {out_path}")
    except Exception as e:
        # Fallback sans pandas
        import csv
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            if matches:
                writer = csv.DictWriter(f, fieldnames=list(matches[0].keys()))
                writer.writeheader()
                writer.writerows(matches)
        print(f"[OK] {len(matches)} entrées → {out_path} (fallback CSV)")


def print_report(matches: list[dict], lnr_total: int) -> None:
    """Affiche les stats de matching et les positions fines détectées."""
    from collections import Counter

    total = len(matches)
    pct = round(total / lnr_total * 100, 1) if lnr_total > 0 else 0

    print(f"\n{'='*60}")
    print(f"  EXTRACT SB POSITIONS — Rapport matching")
    print(f"{'='*60}")
    print(f"  Joueurs LNR total : {lnr_total}")
    print(f"  Matchés SB        : {total} ({pct}%)")
    print()

    # Par position fine
    by_pos = Counter(m["position_fine"] for m in matches)
    print("  Répartition positions fines :")
    for pos in ["HOOKER", "PROP", "FLANKER", "NUMBER_8", "LOCK",
                "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK"]:
        n = by_pos.get(pos, 0)
        if n > 0:
            print(f"    {pos:15s} : {n}")

    # Par confiance
    by_conf = Counter(m["confidence_match"] for m in matches)
    print()
    print("  Qualité du matching :")
    for conf, n in by_conf.most_common():
        print(f"    {conf:20s} : {n}")

    # Positions fines d'intérêt (HOOKER / NUMBER_8)
    interesting = [m for m in matches if m["position_fine"] in FINE_POSITIONS_OF_INTEREST]
    if interesting:
        print()
        print(f"  Positions fines utiles ({len(interesting)}) :")
        for m in sorted(interesting, key=lambda x: (x["position_fine"], x["name_lnr"])):
            print(f"    [{m['position_fine']:10s}] {m['name_lnr']:25s} ({m['team']}) ← SB: {m['name_sb']}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Extract Statbunker Positions")
    parser.add_argument("--input", type=str, default=None,
                        help="Chemin vers statbunker_raw.json (défaut: data/raw/statbunker_raw.json)")
    parser.add_argument("--players", type=str, default=None,
                        help="Chemin vers players.csv (défaut: data/players.csv)")
    parser.add_argument("--output", type=str, default=None,
                        help="Chemin de sortie CSV (défaut: data/statbunker_positions.csv)")
    parser.add_argument("--report", action="store_true",
                        help="Afficher le rapport de matching détaillé")
    args = parser.parse_args()

    sb_path = Path(args.input) if args.input else RAW_DIR / "statbunker_raw.json"
    players_path = Path(args.players) if args.players else DATA_DIR / "players.csv"
    out_path = Path(args.output) if args.output else DATA_DIR / "statbunker_positions.csv"

    print(f"[INFO] Source SB    : {sb_path}")
    print(f"[INFO] Joueurs LNR  : {players_path}")

    if not sb_path.exists():
        print(f"[ERR] statbunker_raw.json introuvable : {sb_path}")
        print("      Lancer d'abord : python data/scrapers/run_pipeline.py --season 2025-2026")
        print("      Ou : python data/scrapers/scraper_statbunker.py --season 2025-2026")
        sys.exit(1)

    if not players_path.exists():
        print(f"[ERR] players.csv introuvable : {players_path}")
        sys.exit(1)

    sb_players = load_sb_data(sb_path)
    lnr_players = load_lnr_players(players_path)

    print(f"[INFO] {len(sb_players)} joueurs SB chargés, {len(lnr_players)} joueurs LNR")

    matches = match_players(sb_players, lnr_players)

    if args.report or True:  # Toujours afficher le rapport
        print_report(matches, len(lnr_players))

    export_csv(matches, out_path)


if __name__ == "__main__":
    main()
