"""
Sanity Check Export — génère data/sanity_check_{season}.json

Contenu :
  - top20_global        : top 20 toutes positions (rating_final)
  - top10_by_position   : top 10 par groupe de poste
  - outliers            : rating_final top 30% ET confidence < 0.4
  - summary             : statistiques globales

Usage :
    python data/sanity_check.py                        # utilise players_scored.csv ou players.csv
    python data/sanity_check.py --season 2025-2026
    python data/sanity_check.py --csv data/players.csv
"""

import argparse
import json
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np


PLAYER_COLS = [
    "name", "team", "position_group", "nationality",
    "matches_played", "minutes_avg",
    "rating_raw", "confidence", "confidence_badge", "rating",
    "rank_position", "rating_percentile_position",
]


def load_df() -> pd.DataFrame:
    scored = ROOT / "data" / "players_scored.csv"
    raw_csv = ROOT / "data" / "players.csv"
    if scored.exists():
        df = pd.read_csv(scored)
        if "rating" in df.columns:
            return df
    if raw_csv.exists():
        from engine.ratings import calculate_ratings
        df = pd.read_csv(raw_csv)
        return calculate_ratings(df)
    raise FileNotFoundError("Aucun fichier players.csv ou players_scored.csv trouvé")


def player_record(row: pd.Series) -> dict:
    rec = {}
    for col in PLAYER_COLS:
        val = row.get(col)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            rec[col] = None
        elif isinstance(val, (np.integer,)):
            rec[col] = int(val)
        elif isinstance(val, (np.floating,)):
            rec[col] = round(float(val), 2)
        elif isinstance(val, (np.bool_,)):
            rec[col] = bool(val)
        else:
            rec[col] = val
    # minutes_total pour lisibilité
    mp = row.get("matches_played") or 0
    ma = row.get("minutes_avg") or 0
    rec["minutes_total"] = round(float(mp) * float(ma), 0)
    # coverage_core : fraction métriques core non-null
    from engine.ratings import load_weights
    try:
        w = load_weights()
        pg = row.get("position_group", "")
        core = list(w.get(pg, {}).keys())
        if core:
            rec["coverage_core"] = round(
                sum(1 for m in core if m in row.index and pd.notna(row[m])) / len(core), 2
            )
        else:
            rec["coverage_core"] = None
    except Exception:
        rec["coverage_core"] = None
    return rec


def build_sanity_check(df: pd.DataFrame, season: str | None = None) -> dict:
    # Détecter la saison si disponible
    if season is None and "season" in df.columns:
        seasons = df["season"].dropna().unique()
        season = str(seasons[0]) if len(seasons) == 1 else "multi"

    # --- Top 20 global ---
    top20 = df.nlargest(20, "rating")
    top20_records = [player_record(row) for _, row in top20.iterrows()]

    # --- Top 10 par poste ---
    top10_by_pos = {}
    for pg in sorted(df["position_group"].dropna().unique()):
        grp = df[df["position_group"] == pg].nlargest(10, "rating")
        top10_by_pos[pg] = [player_record(row) for _, row in grp.iterrows()]

    # --- Outliers : top 30% rating ET confidence < 0.4 ---
    rating_p70 = float(df["rating"].quantile(0.70))
    has_conf = "confidence" in df.columns
    if has_conf:
        outliers_df = df[(df["rating"] >= rating_p70) & (df["confidence"] < 0.40)]
    else:
        outliers_df = pd.DataFrame()
    if not outliers_df.empty and "rating" in outliers_df.columns:
        outliers_df = outliers_df.sort_values("rating", ascending=False)
    outliers = [player_record(row) for _, row in outliers_df.iterrows()]

    # --- Summary ---
    summary = {
        "season": season,
        "n_players": len(df),
        "n_teams": int(df["team"].nunique()),
        "n_position_groups": int(df["position_group"].nunique()),
        "rating_mean": round(float(df["rating"].mean()), 2),
        "rating_std": round(float(df["rating"].std()), 2),
        "rating_min": round(float(df["rating"].min()), 2),
        "rating_max": round(float(df["rating"].max()), 2),
        "rating_p70_threshold": round(rating_p70, 2),
        "n_outliers": len(outliers),
    }
    if has_conf:
        summary["confidence_mean"] = round(float(df["confidence"].mean()), 3)
        summary["n_low_sample"] = int((df["confidence"] < 0.40).sum())
        summary["pct_low_sample"] = round(summary["n_low_sample"] / len(df) * 100, 1)
    if "rating_raw" in df.columns:
        summary["shrinkage_mean_delta"] = round(float((df["rating_raw"] - df["rating"]).abs().mean()), 2)
        summary["shrinkage_max_delta"] = round(float((df["rating_raw"] - df["rating"]).abs().max()), 2)

    return {
        "summary": summary,
        "top20_global": top20_records,
        "top10_by_position": top10_by_pos,
        "outliers_low_confidence": outliers,
    }


def main():
    parser = argparse.ArgumentParser(description="Sanity Check Export")
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--season", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv)
        if "rating" not in df.columns:
            from engine.ratings import calculate_ratings
            df = calculate_ratings(df)
    else:
        df = load_df()

    result = build_sanity_check(df, season=args.season)
    season_label = result["summary"].get("season") or "unknown"
    out_path = Path(args.output) if args.output else ROOT / "data" / f"sanity_check_{season_label}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    s = result["summary"]
    print(f"\n[OK] Sanity check ecrit -> {out_path}")
    print(f"     Saison     : {s.get('season')}")
    print(f"     Joueurs    : {s['n_players']}  |  Equipes : {s['n_teams']}")
    print(f"     Rating     : mean={s['rating_mean']:.1f}  std={s['rating_std']:.1f}  "
          f"[{s['rating_min']:.1f} - {s['rating_max']:.1f}]")
    if "confidence_mean" in s:
        print(f"     Confiance  : mean={s['confidence_mean']:.2f}  "
              f"low_sample={s['n_low_sample']} ({s['pct_low_sample']}%)")
    if "shrinkage_mean_delta" in s:
        print(f"     Shrinkage  : mean_delta={s['shrinkage_mean_delta']:.2f}  "
              f"max_delta={s['shrinkage_max_delta']:.2f}")
    OUTLIER_WARNING_THRESHOLD = 30
    n_out = s['n_outliers']
    outlier_flag = f" [WARN: > {OUTLIER_WARNING_THRESHOLD}]" if n_out > OUTLIER_WARNING_THRESHOLD else ""
    print(f"     Outliers   : {n_out} (top30% rating + conf<0.4){outlier_flag}")

    print(f"\n     Top 5 global :")
    for i, p in enumerate(result["top20_global"][:5], 1):
        print(f"       {i}. {p['name']:25s} {p['position_group']:10s} {p['team']:20s} "
              f"rating={p['rating']}  raw={p.get('rating_raw')}  conf={p.get('confidence')}")


if __name__ == "__main__":
    main()
