"""
Calcule un score de consistance par joueur à partir du match history.

Méthode : coefficient de variation inversé (1 - CV) sur les stats clés
  - CV = écart-type / moyenne  (mesure l'irrégularité)
  - consistency_raw = 1 - CV  (0 = très irrégulier, 1 = très constant)
  - Normalisé p5/p95 → [0, 100]

Un joueur qui performe 10 plaquages/80 à chaque match → score ≈ 100
Un joueur qui alterne 0 et 20 → score ≈ 0

Usage : python data/scrapers/compute_consistency.py
Output : data/player_consistency.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HISTORY_PATH = Path(__file__).parent.parent / "raw" / "lnr_match_history.json"
OUT_PATH = Path(__file__).parent.parent / "player_consistency.csv"

METRICS = ["tackles_success", "offloads", "line_breaks", "turnovers_won"]
MIN_MATCHES = 3   # minimum de matchs pour calculer une variance fiable
MIN_MINUTES = 20  # minutes minimum par match pour inclure le match


def _per80(val, minutes):
    if minutes and minutes >= MIN_MINUTES:
        return (val or 0) / minutes * 80
    return None


def main():
    with open(HISTORY_PATH, encoding="utf-8") as f:
        matches = json.load(f)

    # Récupère les stats par match pour chaque joueur
    player_matches: dict[str, list[dict]] = {}

    for match in matches:
        for p in match.get("players", []):
            slug = p.get("lnr_slug")
            mins = p.get("minutes_played", 0) or 0
            if not slug or mins < MIN_MINUTES:
                continue

            row = {m: _per80(p.get(m, 0), mins) for m in METRICS}
            row = {k: v for k, v in row.items() if v is not None}
            if not row:
                continue

            if slug not in player_matches:
                player_matches[slug] = []
            player_matches[slug].append({
                "lnr_slug": slug,
                "name": p.get("name", ""),
                "team": p.get("team", ""),
                "minutes": mins,
                **row,
            })

    # Calcule le score de consistance par joueur
    records = []
    for slug, game_list in player_matches.items():
        if len(game_list) < MIN_MATCHES:
            continue

        gdf = pd.DataFrame(game_list)
        cvs = []
        for metric in METRICS:
            if metric not in gdf.columns:
                continue
            vals = gdf[metric].dropna().values
            if len(vals) < 2:
                continue
            mean = vals.mean()
            std = vals.std(ddof=1)
            # CV = 0 si pas de variance (parfaitement constant)
            cv = (std / mean) if mean > 0.5 else 0.0
            cvs.append(min(cv, 2.0))  # cap à 2 pour éviter les outliers extrêmes

        if not cvs:
            continue

        avg_cv = np.mean(cvs)
        consistency_raw = 1.0 - (avg_cv / 2.0)  # normalise CV [0,2] → [0,1] inversé

        records.append({
            "lnr_slug": slug,
            "name": gdf["name"].iloc[-1],
            "team": gdf["team"].iloc[-1],
            "n_matches_consistency": len(game_list),
            "consistency_raw": round(consistency_raw, 4),
        })

    if not records:
        print("Aucun joueur avec assez de matchs.")
        return

    df = pd.DataFrame(records)

    # Normalisation p5/p95 → [0, 100]
    lo = df["consistency_raw"].quantile(0.05)
    hi = df["consistency_raw"].quantile(0.95)
    if hi > lo:
        df["axis_consistency"] = ((df["consistency_raw"] - lo) / (hi - lo) * 100).clip(0, 100).round(1)
    else:
        df["axis_consistency"] = 50.0

    df = df.sort_values("axis_consistency", ascending=False)

    df.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"Consistance calculée : {len(df)} joueurs → {OUT_PATH}")
    print(f"  Distribution : min={df['axis_consistency'].min():.1f} | "
          f"médiane={df['axis_consistency'].median():.1f} | "
          f"max={df['axis_consistency'].max():.1f}")


if __name__ == "__main__":
    main()
