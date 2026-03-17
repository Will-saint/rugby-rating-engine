"""
Combine les players_scored.csv de toutes les saisons en un seul fichier.

Output :
  data/players_all_seasons.csv  — tous les joueurs, toutes saisons, avec colonne 'season'

Usage :
    python data/scrapers/combine_seasons.py
    python data/scrapers/combine_seasons.py --seasons 2022-2023 2023-2024 2024-2025 2025-2026
    python data/scrapers/combine_seasons.py --output data/players_all_seasons.csv
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

SEASONS_DIR = ROOT / "data" / "seasons"
POST_COVID_SEASONS = [
    "2020-2021", "2021-2022", "2022-2023",
    "2023-2024", "2024-2025", "2025-2026",
]


def main():
    parser = argparse.ArgumentParser(description="Combine toutes les saisons en un CSV")
    parser.add_argument("--seasons", nargs="+", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError:
        print("[ERR] pandas requis")
        sys.exit(1)

    seasons = args.seasons if args.seasons else POST_COVID_SEASONS
    output_path = Path(args.output) if args.output else ROOT / "data" / "players_all_seasons.csv"

    frames = []
    for season in seasons:
        scored = SEASONS_DIR / season / "players_scored.csv"
        if not scored.exists():
            print(f"[WARN] {scored} introuvable — skip")
            continue
        df = pd.read_csv(scored)
        # S'assurer que la colonne season est correcte
        df["season"] = season
        frames.append(df)
        print(f"[OK]   {season} : {len(df)} joueurs")

    if not frames:
        print("[ERR] Aucune saison disponible")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)

    # Ordre : season + player_id + nom
    combined = combined.sort_values(["season", "name"], ignore_index=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)

    n_seasons = combined["season"].nunique()
    n_players_unique = combined["lnr_id"].nunique() if "lnr_id" in combined.columns else combined["name"].nunique()
    n_records = len(combined)

    print(f"\n[OK] {output_path}")
    print(f"     {n_seasons} saisons · {n_records} entrées · {n_players_unique} joueurs uniques")

    # Stats rapides par saison
    print("\nRésumé par saison :")
    for s, grp in combined.groupby("season"):
        avg = grp["rating"].mean() if "rating" in grp.columns else 0
        print(f"  {s} : {len(grp)} joueurs, note moy {avg:.1f}")


if __name__ == "__main__":
    main()
