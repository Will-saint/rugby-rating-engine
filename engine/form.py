"""
engine/form.py — Calcul de la forme récente par joueur.

Sources :
  - data/raw/lnr_match_history.json  (matchs j1-j18, stats par match)
  - data/player_form.csv             (résumé form window=5 matches, pré-calculé)

Produit :
  - form_score   [0,100] : score pondéré sur les 5 derniers matchs (decay exponentiel)
  - form_trend   : "↗" / "↘" / "→"  comparaison 3 derniers vs 3 précédents
  - form_matches : nombre de matchs récents utilisés pour le calcul
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
HISTORY_PATH = ROOT / "data" / "raw" / "lnr_match_history.json"
FORM_CSV_PATH = ROOT / "data" / "player_form.csv"

# Métriques disponibles dans le match history + leur poids relatif
# (Uniformes ici car on ne connaît pas le poste au niveau per-match)
_MATCH_METRICS = {
    "tackles_success":  0.35,
    "line_breaks":      0.25,
    "offloads":         0.20,
    "turnovers_won":    0.20,
}

# Mapping vers les noms de colonnes player_form.csv
_FORM_CSV_MAP = {
    "form_tackles_per80":    "tackles_per80",
    "form_line_breaks_per80": "line_breaks_per80",
    "form_offloads_per80":   "offloads_per80",
    "form_turnovers_per80":  "turnovers_won_per80",
}


@lru_cache(maxsize=1)
def _load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _per80(value: float, minutes: float) -> float:
    """Normalise une stat en /80 minutes. Évite division par 0."""
    if minutes < 1:
        return 0.0
    return value * 80.0 / minutes


def build_player_match_df() -> pd.DataFrame:
    """
    Construit un DataFrame plat avec une ligne par (joueur × match).
    Colonnes : lnr_slug, date, round, minutes_played + métriques /80.
    """
    fixtures = _load_history()
    rows = []
    for fix in fixtures:
        date = fix.get("date", "")
        rnd  = fix.get("round", "")
        for p in fix.get("players", []):
            slug = p.get("lnr_slug", "")
            minutes = float(p.get("minutes_played", 0) or 0)
            if minutes < 5:
                continue  # trop peu de temps pour être significatif
            rows.append({
                "lnr_slug":       slug,
                "date":           date,
                "round":          rnd,
                "minutes_played": minutes,
                "tackles_per80":        _per80(float(p.get("tackles_success", 0) or 0), minutes),
                "line_breaks_per80":    _per80(float(p.get("line_breaks", 0) or 0), minutes),
                "offloads_per80":       _per80(float(p.get("offloads", 0) or 0), minutes),
                "turnovers_won_per80":  _per80(float(p.get("turnovers_won", 0) or 0), minutes),
                "tries_per80":          _per80(float(p.get("tries", 0) or 0), minutes),
                "points_per80":         _per80(float(p.get("points", 0) or 0), minutes),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values(["lnr_slug", "date"])
    return df


@lru_cache(maxsize=1)
def _cached_match_df() -> pd.DataFrame:
    return build_player_match_df()


def _match_score(row: pd.Series) -> float:
    """Score pondéré sur les métriques disponibles (somme des poids = 1)."""
    return (
        row.get("tackles_per80",       0) * 0.35 +
        row.get("line_breaks_per80",   0) * 0.25 +
        row.get("offloads_per80",      0) * 0.20 +
        row.get("turnovers_won_per80", 0) * 0.20
    )


def compute_form(n_recent: int = 5, decay: float = 0.7) -> pd.DataFrame:
    """
    Calcule form_score et form_trend pour chaque joueur.

    Args:
        n_recent : nombre de matchs récents à utiliser
        decay    : poids exponentiel décroissant (match le plus récent = 1.0,
                   le suivant = decay, puis decay², etc.)

    Returns:
        DataFrame indexé par lnr_slug avec colonnes :
          form_score, form_trend, form_matches, form_scores_list (liste JSON)
    """
    match_df = _cached_match_df()
    if match_df.empty:
        return pd.DataFrame(columns=["lnr_slug", "form_score", "form_trend", "form_matches"])

    # Calcul du score brut par match
    match_df["_raw_score"] = match_df.apply(_match_score, axis=1)

    results = []
    for slug, grp in match_df.groupby("lnr_slug"):
        grp = grp.sort_values("date", ascending=False)  # plus récent en premier
        recent  = grp.head(n_recent)["_raw_score"].values
        n_used  = len(recent)

        if n_used == 0:
            continue

        # Decay exponentiel : poids[0]=1.0, poids[1]=decay, poids[2]=decay², ...
        weights = np.array([decay ** i for i in range(n_used)])
        weighted_avg = float(np.average(recent, weights=weights))

        # Trend : 3 derniers vs 3 précédents
        last3 = grp["_raw_score"].values[:3]
        prev3 = grp["_raw_score"].values[3:6]

        if len(prev3) > 0:
            delta = last3.mean() - prev3.mean()
            if delta > 0.3:
                trend = "↗"
            elif delta < -0.3:
                trend = "↘"
            else:
                trend = "→"
        else:
            trend = "→"  # pas assez de matchs pour calculer la tendance

        # Historique brut pour sparkline (5 derniers matchs chronologiquement)
        sparkline_scores = grp.head(n_recent)["_raw_score"].values[::-1].tolist()

        results.append({
            "lnr_slug":     slug,
            "form_raw":     round(weighted_avg, 3),
            "form_trend":   trend,
            "form_matches": n_used,
            "_scores_list": sparkline_scores,
        })

    form_df = pd.DataFrame(results)
    if form_df.empty:
        return form_df

    # Normaliser form_raw en [0, 100] (p5/p95 globaux)
    lo = float(np.percentile(form_df["form_raw"], 5))
    hi = float(np.percentile(form_df["form_raw"], 95))
    if hi - lo < 1e-9:
        form_df["form_score"] = 50.0
    else:
        form_df["form_score"] = ((form_df["form_raw"] - lo) / (hi - lo) * 100).clip(0, 100).round(1)

    # Normaliser chaque score de la sparkline
    all_scores = [s for row in form_df["_scores_list"] for s in row]
    if all_scores:
        s_lo = float(np.percentile(all_scores, 5))
        s_hi = float(np.percentile(all_scores, 95))
        def _norm_list(lst):
            if s_hi - s_lo < 1e-9:
                return [50.0] * len(lst)
            return [round(min(100, max(0, (v - s_lo) / (s_hi - s_lo) * 100)), 1) for v in lst]
        form_df["form_scores_list"] = form_df["_scores_list"].apply(_norm_list)
    else:
        form_df["form_scores_list"] = form_df["_scores_list"]

    return form_df[["lnr_slug", "form_score", "form_trend", "form_matches", "form_scores_list"]]


@lru_cache(maxsize=1)
def get_form_df() -> pd.DataFrame:
    """Cached version of compute_form()."""
    return compute_form()


def get_player_sparkline(lnr_slug: str) -> list[float]:
    """
    Retourne la liste des scores normalisés des 5 derniers matchs (du plus ancien au plus récent).
    Vide si joueur non trouvé.
    """
    df = get_form_df()
    if df.empty or lnr_slug not in df["lnr_slug"].values:
        return []
    row = df[df["lnr_slug"] == lnr_slug].iloc[0]
    return row.get("form_scores_list", [])
