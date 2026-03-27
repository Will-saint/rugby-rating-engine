"""
Rugby Rating Engine v4 — Architecture 7 axes (inspiré Naim/M2PSTB).

Pipeline :
  1. Discipline per80 = (0.6·YC + 1.2·OC + 2.0·RC) / min_total * 80
  2. Min-max [p5, p95] pour chaque métrique dans le groupe de poste.
  3. 6 axes (0-100) :
       Course      = line_breaks_per80  (franchissements)
       Distribution = offloads_per80    (jeu de bras)
       Kicking     = points_scored_per80 (impact offensif/points)
       Physique    = tackles_per80      (puissance défensive)
       Rigueur     = 100 - disc_per80   (discipline, inversé)
       Danger      = 0.6·tries_per80 + 0.4·turnovers_won_per80
  4. score_raw = Σ(axe_i · poids_position_i) / 100   → [0, 100]
  5. conf = clip(minutes_total / p90_minutes_poste, 0, 1)
  6. score_final = conf · score_raw + (1 − conf) · 50
  7. rating = clip(40 + 0.6 · score_final, 40, 99)

Poids de position issus des travaux de Naim (categ_weight_cluster1.csv),
Mêlée redistribuée sur Rigueur (pas de données disponibles en Top14 public).
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Poids des 6 axes par poste (issus de Naim, adaptés Top14)
# Somme = 100 pour chaque poste.
# Mêlée = 0 (données indisponibles) → poids redistribués sur Rigueur.
# ---------------------------------------------------------------------------

NAIM_POS_WEIGHTS: dict[str, dict[str, float]] = {
    # Backs
    "CENTRE":     {"course": 29.1, "distrib": 27.6, "kicking":  7.3, "physique":  4.5, "rigueur": 14.4, "danger": 17.1},
    "SCRUM_HALF": {"course": 14.7, "distrib": 34.4, "kicking":  7.5, "physique":  9.5, "rigueur": 16.0, "danger": 17.9},
    "FLY_HALF":   {"course": 14.5, "distrib": 26.9, "kicking": 24.9, "physique":  3.9, "rigueur": 14.6, "danger": 15.2},
    "WINGER":     {"course": 34.6, "distrib": 18.6, "kicking":  1.1, "physique":  3.8, "rigueur": 16.3, "danger": 25.7},
    "FULLBACK":   {"course": 25.5, "distrib": 21.7, "kicking": 16.0, "physique":  6.6, "rigueur": 10.9, "danger": 19.2},
    # Forwards — Mêlée (FL 6.1, N8 4.3, H 10.6, P 13.3, L 16.9) → Rigueur
    "BACK_ROW":   {"course": 25.3, "distrib": 19.9, "kicking":  0.0, "physique":  3.0, "rigueur": 37.5, "danger": 14.4},
    "FRONT_ROW":  {"course": 14.1, "distrib":  4.8, "kicking":  0.0, "physique": 15.0, "rigueur": 54.8, "danger": 11.3},
    "LOCK":       {"course": 13.8, "distrib": 15.0, "kicking":  0.0, "physique":  5.5, "rigueur": 59.2, "danger":  6.5},
}

# Alias → noms de colonnes UI (rétrocompatibilité)
AXIS_COLS = {
    "course":   "axis_att",    # Course → CARRY
    "distrib":  "axis_ctrl",   # Distribution → DIST
    "kicking":  "axis_kick",   # Kicking → KICK
    "physique": "axis_def",    # Physique → DEF
    "rigueur":  "axis_disc",   # Rigueur → DISC (discipline)
    "danger":   "axis_pow",    # Danger → DANGER
}

POSITION_GROUP_LABEL = {
    "FRONT_ROW":  "1ère Ligne",
    "LOCK":       "2ème Ligne",
    "BACK_ROW":   "3ème Ligne",
    "SCRUM_HALF": "Demi de mêlée",
    "FLY_HALF":   "Ouvreur",
    "WINGER":     "Ailier",
    "CENTRE":     "Centre",
    "FULLBACK":   "Arrière",
}

POSITION_ABBR = {
    "FRONT_ROW":  "1L",  "LOCK":      "2L",  "BACK_ROW":  "3L",
    "SCRUM_HALF": "9",   "FLY_HALF":  "10",
    "WINGER":     "AIL", "CENTRE":    "CTR", "FULLBACK":  "ARR",
}

# Pour get_rating_breakdown (rétrocompatibilité)
POS_WEIGHTS = {pg: {"metrics": {}, "w_disc": 0.2} for pg in NAIM_POS_WEIGHTS}

POSITION_GROUP_LABEL = {
    "FRONT_ROW":  "1ère Ligne",
    "LOCK":       "2ème Ligne",
    "BACK_ROW":   "3ème Ligne",
    "SCRUM_HALF": "Demi de mêlée",
    "FLY_HALF":   "Ouvreur",
    "WINGER":     "Ailier",
    "CENTRE":     "Centre",
    "FULLBACK":   "Arrière",
}

POSITION_ABBR = {
    "FRONT_ROW":  "1L",  "LOCK":      "2L",  "BACK_ROW":  "3L",
    "SCRUM_HALF": "9",   "FLY_HALF":  "10",
    "WINGER":     "AIL", "CENTRE":    "CTR", "FULLBACK":  "ARR",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _zscore(values: np.ndarray, clip: float = 3.0) -> np.ndarray:
    """Z-score d'un vecteur, clipé à ±clip. Retourne 0 si std=0."""
    mu, sigma = values.mean(), values.std()
    if sigma < 1e-9:
        return np.zeros_like(values, dtype=float)
    return np.clip((values - mu) / sigma, -clip, clip)


def _minmax(arr: np.ndarray, p_low: float = 5.0, p_high: float = 95.0) -> np.ndarray:
    """
    Normalise arr en [0, 100] par percentiles p_low/p_high (méthode Naim).
    Valeurs sous p_low → 0, au-dessus p_high → 100.
    """
    lo = float(np.percentile(arr, p_low))
    hi = float(np.percentile(arr, p_high))
    if hi - lo < 1e-9:
        return np.full_like(arr, 50.0, dtype=float)
    normed = (arr - lo) / (hi - lo) * 100.0
    return np.clip(normed, 0.0, 100.0)


def _minutes_bucket(m: float) -> str:
    if m >= 1400: return "Haute"
    if m >= 800:  return "Bonne"
    if m >= 400:  return "Moyenne"
    return "Basse"


def _get_col(group: pd.DataFrame, col: str) -> np.ndarray:
    """Retourne la colonne comme float, rempli par la médiane si NaN."""
    if col not in group.columns:
        return np.zeros(len(group), dtype=float)
    s = group[col].fillna(0.0)
    return s.values.astype(float)


# ---------------------------------------------------------------------------
# Calcul principal — Architecture Naim v4
# ---------------------------------------------------------------------------

def calculate_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Architecture 7 axes inspirée de Naim (M2PSTB) :
      Course, Distribution, Kicking, Physique, Rigueur, Danger.
    Normalisation min-max [p5, p95] par groupe de poste.
    Poids de position de Naim (categ_weight_cluster1, adaptés Top14).
    """
    result_parts: list[pd.DataFrame] = []

    for pg, pos_w in NAIM_POS_WEIGHTS.items():
        group = df[df["position_group"] == pg].copy()
        if group.empty:
            continue

        # ----------------------------------------------------------------
        # 0. Minutes totales
        # ----------------------------------------------------------------
        mt = _get_col(group, "minutes_total")
        if mt.sum() == 0 and "matches_played" in group.columns:
            mt = _get_col(group, "matches_played") * _get_col(group, "minutes_avg")

        # ----------------------------------------------------------------
        # 1. Métriques brutes → min-max [0, 100] par poste
        # ----------------------------------------------------------------
        lb   = _minmax(_get_col(group, "line_breaks_per80"))    # franchissements
        off  = _minmax(_get_col(group, "offloads_per80"))       # offloads
        pts  = _minmax(_get_col(group, "points_scored_per80"))  # points (kicks+essais)
        tack = _minmax(_get_col(group, "tackles_per80"))        # plaquages
        tow  = _minmax(_get_col(group, "turnovers_won_per80"))  # grattages

        # tries_per80 : calculé si dispo (LNR raw), sinon estimé via points
        tries_raw = _get_col(group, "tries_per80")
        if tries_raw.sum() == 0 and "tries_total" in group.columns:
            t_tot = _get_col(group, "tries_total")
            tries_raw = np.where(mt > 0, t_tot / mt * 80, 0.0)
        tries = _minmax(tries_raw)

        # ----------------------------------------------------------------
        # 2. Discipline per80 → axe Rigueur (inversé : 0 carton = 100)
        # ----------------------------------------------------------------
        yc = _get_col(group, "yellow_cards")
        oc = _get_col(group, "orange_cards")
        rc = _get_col(group, "red_cards")
        disc_raw = np.where(mt > 0, (0.6 * yc + 1.2 * oc + 2.0 * rc) / mt * 80, 0.0)
        rigueur  = 100.0 - _minmax(disc_raw, p_low=0, p_high=95)  # inversé

        # ----------------------------------------------------------------
        # 3. Scores par axe [0, 100]
        # ----------------------------------------------------------------
        ax_course  = lb                                   # Course
        ax_distrib = off                                  # Distribution
        ax_kicking = pts                                  # Kicking
        ax_physique = tack                                # Physique
        ax_rigueur  = rigueur                             # Rigueur (disc inversée)
        ax_danger   = 0.6 * tries + 0.4 * tow            # Danger

        # ----------------------------------------------------------------
        # 4. Score global pondéré par poste (Naim) → [0, 100]
        # ----------------------------------------------------------------
        w = pos_w
        score_raw = (
            w["course"]  * ax_course   +
            w["distrib"] * ax_distrib  +
            w["kicking"] * ax_kicking  +
            w["physique"] * ax_physique +
            w["rigueur"] * ax_rigueur  +
            w["danger"]  * ax_danger
        ) / 100.0  # les poids somment à ~100

        # ----------------------------------------------------------------
        # 5. Fiabilité (Bayesian shrinkage vers 50)
        # ----------------------------------------------------------------
        p90 = float(np.percentile(mt[mt > 0], 90)) if (mt > 0).sum() >= 5 else 1200.0
        p90 = max(p90, 400.0)
        conf        = np.clip(mt / p90, 0.0, 1.0)
        score_final = conf * score_raw + (1.0 - conf) * 50.0

        # ----------------------------------------------------------------
        # 6. Rating FIFA → [40, 99]
        # ----------------------------------------------------------------
        group["rating_raw"] = np.round(np.clip(40.0 + 0.6 * score_raw,   40.0, 99.0), 1)
        group["rating"]     = np.round(np.clip(40.0 + 0.6 * score_final, 40.0, 99.0), 1)
        group["confidence"] = np.round(conf, 3)

        # ----------------------------------------------------------------
        # 7. Axes visuels [0, 100] → colonnes axis_*
        # ----------------------------------------------------------------
        group["axis_att"]  = np.round(ax_course).astype(int)    # Course
        group["axis_ctrl"] = np.round(ax_distrib).astype(int)   # Distribution
        group["axis_kick"] = np.round(ax_kicking).astype(int)   # Kicking
        group["axis_def"]  = np.round(ax_physique).astype(int)  # Physique
        group["axis_disc"] = np.round(ax_rigueur).astype(int)   # Rigueur
        group["axis_pow"]  = np.round(ax_danger).astype(int)    # Danger

        result_parts.append(group)

    combined = pd.concat(result_parts).sort_index()

    # ----------------------------------------------------------------
    # 8. Métadonnées UI
    # ----------------------------------------------------------------
    combined["position_label"] = combined["position_group"].map(POSITION_GROUP_LABEL)
    combined["position_abbr"]  = combined["position_group"].map(POSITION_ABBR)

    combined["confidence_score"] = (combined["confidence"] * 100).round(0).clip(upper=100).fillna(50).astype(int)

    def _conf_badge(c: float) -> str:
        if c >= 0.70: return "Haute"
        if c >= 0.40: return "Moyenne"
        return "Basse"
    combined["confidence_badge"] = combined["confidence"].apply(_conf_badge)
    combined["low_sample"]       = combined["confidence"] < 0.40

    if "matches_played" in combined.columns and "minutes_avg" in combined.columns:
        mt_ui = combined["matches_played"].fillna(0) * combined["minutes_avg"].fillna(0)
        combined["minutes_bucket"] = mt_ui.apply(_minutes_bucket)
    else:
        combined["minutes_bucket"] = "Basse"

    mp_col = "matches_played"
    if mp_col in combined.columns:
        combined["data_insufficient"] = (
            (combined[mp_col].fillna(0) < 5) | (combined["confidence"] < 0.25)
        )
    else:
        combined["data_insufficient"] = combined["confidence"] < 0.25

    combined["rank_position"] = combined.groupby("position_group")["rating"].rank(
        ascending=False, method="min"
    ).fillna(999).astype(int)

    combined["rating_percentile_position"] = combined.groupby("position_group")["rating"].transform(
        lambda s: s.rank(pct=True) * 100
    ).round(1)

    return combined


# ---------------------------------------------------------------------------
# Breakdown explicatif (pour page Player Cards)
# ---------------------------------------------------------------------------

def get_rating_breakdown(player_row: pd.Series) -> list[dict]:
    """
    Retourne la contribution de chaque métrique pour ce joueur.
    Recalcule les Z-scores à partir du DataFrame d'origine si disponible.
    (Limité : retourne les valeurs brutes si pas de contexte poste.)
    """
    pg  = player_row.get("position_group", "")
    cfg = POS_WEIGHTS.get(pg, {})
    if not cfg:
        return []
    result = []
    for metric, weight in cfg["metrics"].items():
        val = player_row.get(metric)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        result.append({
            "metric":  metric,
            "value":   round(float(val), 2),
            "weight":  weight,
            "pct":     None,   # Z-score non disponible hors contexte poste
            "contrib": None,
            "negative": False,
        })
    return result


# ---------------------------------------------------------------------------
# Prior historique — blend saison actuelle × moyennes historiques
# ---------------------------------------------------------------------------

_POST_COVID_SEASONS = [
    "2020-2021", "2021-2022", "2022-2023",
    "2023-2024", "2024-2025", "2025-2026",
]


def apply_historical_prior(
    df_current: pd.DataFrame,
    all_seasons_path: str,
    current_season: str = "2025-2026",
    n_prior: int = 2,
) -> pd.DataFrame:
    """
    Ajoute la colonne rating_value = blend(rating_saison, prior_historique).

    alpha dépend du volume de jeu actuel :
      minutes_total >= 800  → alpha = 0.80  (données suffisantes, saison prime)
      300–799               → alpha = 0.50
      < 300                 → alpha = 0.25  (peu de matchs → prior prime)

    Pour les joueurs sans historique : rating_value = rating (saison pure).
    """
    from pathlib import Path as _Path

    df = df_current.copy()

    if not _Path(all_seasons_path).exists():
        df["rating_value"] = df["rating"]
        df["has_prior"] = False
        return df

    df_all = pd.read_csv(all_seasons_path)
    hist   = df_all[df_all["season"] != current_season].copy()

    if hist.empty:
        df["rating_value"] = df["rating"]
        df["has_prior"] = False
        return df

    # Ordre chronologique
    s_rank = {s: i for i, s in enumerate(_POST_COVID_SEASONS)}
    hist["_rank"] = hist["season"].map(s_rank).fillna(-1)

    # Prior par joueur = moyenne pondérée des N dernières saisons complètes
    # poids : saison la plus récente = N, la plus ancienne = 1
    hist["_key"] = hist["name"].str.strip().str.lower()
    prior_map: dict[str, float] = {}
    for key, grp in hist.groupby("_key"):
        recent  = grp.nlargest(n_prior, "_rank").sort_values("_rank")
        w       = np.arange(1, len(recent) + 1, dtype=float)
        prior_map[key] = round(float(np.average(recent["rating"].values, weights=w)), 1)

    # Minutes totales actuelles
    if "minutes_total" in df.columns:
        mt = df["minutes_total"].fillna(0).values
    else:
        mt = (df["matches_played"].fillna(0) * df["minutes_avg"].fillna(0)).values

    def _alpha(m: float) -> float:
        if m >= 800: return 0.80
        if m >= 300: return 0.50
        return 0.25

    df["_key"] = df["name"].str.strip().str.lower()
    rv, hp = [], []
    for i, (_, row) in enumerate(df.iterrows()):
        prior = prior_map.get(row["_key"])
        if prior is None:
            rv.append(row["rating"])
            hp.append(False)
        else:
            a = _alpha(float(mt[i]))
            rv.append(round(a * row["rating"] + (1.0 - a) * prior, 1))
            hp.append(True)

    df["rating_value"] = rv
    df["has_prior"]    = hp
    df.drop(columns=["_key"], inplace=True)
    return df


# ---------------------------------------------------------------------------
# Team strength
# ---------------------------------------------------------------------------

def get_team_strength(df_rated: pd.DataFrame) -> pd.DataFrame:
    POSITION_WEIGHT = {
        "FRONT_ROW": 1.0, "LOCK": 1.0, "BACK_ROW": 1.1,
        "SCRUM_HALF": 1.2, "FLY_HALF": 1.3,
        "WINGER": 1.0, "CENTRE": 1.1, "FULLBACK": 1.2,
    }

    rows = []
    for team, grp in df_rated.groupby("team"):
        best_per_pos = grp.loc[grp.groupby("position_group")["rating"].idxmax()]

        total_w, weighted_rating = 0.0, 0.0
        for _, player in best_per_pos.iterrows():
            w = POSITION_WEIGHT.get(player["position_group"], 1.0)
            weighted_rating += w * player["rating"]
            total_w += w

        team_rating = round(weighted_rating / total_w, 1) if total_w > 0 else 50.0

        rows.append({
            "team":         team,
            "team_code":    grp["team_code"].iloc[0],
            "team_rating":  team_rating,
            "att_index":    round(best_per_pos["axis_att"].mean(), 1),
            "def_index":    round(best_per_pos["axis_def"].mean(), 1),
            "kick_index":   round(best_per_pos["axis_kick"].mean(), 1),
            "pow_index":    round(best_per_pos["axis_pow"].mean(), 1),
            "player_count": len(grp),
        })

    return pd.DataFrame(rows).sort_values("team_rating", ascending=False).reset_index(drop=True)
