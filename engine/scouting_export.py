"""
engine/scouting_export.py — Export normalisé pour App 4 (Scouting).

Produit un CSV prêt à être ingéré par App 4 sans couplage de code.
Format standardisé et documenté — modifier ici si App 4 change son schéma.

Colonnes exportées (schéma v1) :
  player_id, slug, name, team, nationality, position_group, position_label,
  age, height_cm, weight_kg,
  rating, rating_value, display_rating, rating_intl, matches_intl, team_intl,
  confidence, form_score, form_trend,
  axis_att, axis_def, axis_disc, axis_ctrl, axis_kick, axis_pow,
  tackles_per80, line_breaks_per80, offloads_per80, turnovers_won_per80,
  tries_per80, points_scored_per80,
  matches_played, minutes_total,
  yellow_cards, red_cards,
  export_date, export_season

Usage :
    python -m engine.scouting_export          # génère data/scouting_export.csv
    from engine.scouting_export import generate_export
    generate_export(df_rated, season="2025-2026")
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
EXPORT_PATH = ROOT / "data" / "scouting_export.csv"

# Colonnes exportées dans l'ordre final — None si colonne absente → 0/""
EXPORT_SCHEMA: dict[str, str | None] = {
    # Identifiants
    "lnr_id":            "player_id",
    "lnr_slug":          "slug",
    "name":              "name",
    "team":              "team",
    "nationality":       "nationality",
    "position_group":    "position_group",
    "position_label":    "position_label",
    # Physique
    "age":               "age",
    "height_cm":         "height_cm",
    "weight_kg":         "weight_kg",
    # Notes globales
    "rating":            "rating",
    "rating_value":      "rating_value",
    "display_rating":    "display_rating",
    "rating_intl":       "rating_intl",
    "matches_intl":      "matches_intl",
    "team_intl":         "team_intl",
    "confidence":        "confidence",
    # Forme
    "form_score":        "form_score",
    "form_trend":        "form_trend",
    # Axes visuels
    "axis_att":          "axis_att",
    "axis_def":          "axis_def",
    "axis_disc":         "axis_disc",
    "axis_ctrl":         "axis_ctrl",
    "axis_kick":         "axis_kick",
    "axis_pow":          "axis_pow",
    # Stats brutes /80
    "tackles_per80":         "tackles_per80",
    "line_breaks_per80":     "line_breaks_per80",
    "offloads_per80":        "offloads_per80",
    "turnovers_won_per80":   "turnovers_won_per80",
    "tries_per80":           "tries_per80",
    "points_scored_per80":   "points_scored_per80",
    # Volume
    "matches_played":    "matches_played",
    "minutes_total":     "minutes_total",
    # Discipline (brutes — pour filtrage App 4)
    "yellow_cards":      "yellow_cards",
    "red_cards":         "red_cards",
}


def generate_export(
    df: pd.DataFrame,
    season: str = "2025-2026",
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Génère le fichier scouting_export.csv à partir du DataFrame noté.

    Args:
        df          : DataFrame produit par calculate_ratings() + apply_historical_prior()
        season      : saison courante (ajoutée comme colonne export_season)
        output_path : chemin de sortie (défaut : data/scouting_export.csv)

    Returns:
        DataFrame exporté (pour usage programmatique)
    """
    if output_path is None:
        output_path = EXPORT_PATH

    export_rows: dict[str, list] = {v: [] for v in EXPORT_SCHEMA.values()}
    export_rows["export_date"]   = []
    export_rows["export_season"] = []

    today_str = date.today().isoformat()

    for _, row in df.iterrows():
        for src_col, dst_col in EXPORT_SCHEMA.items():
            val = row.get(src_col)
            export_rows[dst_col].append(val)
        export_rows["export_date"].append(today_str)
        export_rows["export_season"].append(season)

    out = pd.DataFrame(export_rows)

    # Nettoyage : remplacer NaN par valeurs par défaut selon le type
    str_cols = ["slug", "name", "team", "nationality", "position_group",
                "position_label", "team_intl", "form_trend", "export_date", "export_season"]
    for c in str_cols:
        if c in out.columns:
            out[c] = out[c].fillna("").astype(str)

    float_cols = ["rating", "rating_value", "display_rating", "rating_intl",
                  "confidence", "form_score",
                  "axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow",
                  "tackles_per80", "line_breaks_per80", "offloads_per80",
                  "turnovers_won_per80", "tries_per80", "points_scored_per80"]
    for c in float_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0).round(2)

    int_cols = ["player_id", "age", "height_cm", "weight_kg", "matches_intl",
                "matches_played", "minutes_total", "yellow_cards", "red_cards"]
    for c in int_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

    out = out.sort_values("display_rating", ascending=False).reset_index(drop=True)

    out.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[EXPORT] {len(out)} joueurs exportés → {output_path}")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    from engine.ratings import calculate_ratings, apply_historical_prior

    players_csv = ROOT / "data" / "players.csv"
    if not players_csv.exists():
        print("data/players.csv introuvable — lance le pipeline d'abord.")
        sys.exit(1)

    df_raw = pd.read_csv(players_csv)
    df_rated = calculate_ratings(df_raw)
    df_rated = apply_historical_prior(df_rated, str(ROOT / "data" / "players_all_seasons.csv"))
    generate_export(df_rated)
