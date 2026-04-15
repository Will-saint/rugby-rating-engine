"""
Rugby Rating Engine v6 — Weights directs par métrique + discipline malus.

Pipeline :
  1. Calcul kick_points_per80 = (points_scored_per80 - tries_per80*5).clip(0)
  2. Min-max [p5, p95] pour chaque métrique dans le groupe de poste.
  3. score_raw = Σ(métrique_normalisée * poids) → [0, 100]
     Poids = proportions directes par métrique (somme = 1.0 par poste).
  4. Confiance (step function) :
       ≥600 min → 1.00 | ≥300 min → 0.75 | ≥150 min → 0.60 | <150 min → 0.50
  5. score_final = conf * score_raw + (1-conf) * 50
  6. rating_raw = clip(40 + 0.6 * score_raw, 40, 99)
     rating     = clip(40 + 0.6 * score_final, 40, 99)
  7. Discipline malus (appliqué APRÈS le rating) :
       YC: -2pts | OC: -3pts | RC: -8pts | cap: -10pts
     rating = clip(rating - malus, 40, 99)

Axes visuels (affichage carte/radar — indépendants du scoring) :
  axis_att  = minmax(line_breaks_per80)
  axis_def  = minmax(tackles_per80)
  axis_disc = 100 - malus*10   (100=clean, 0=max cartons)
  axis_ctrl = minmax(offloads_per80)
  axis_kick = minmax(kick_points_per80)
  axis_pow  = 0.6*minmax(tries_per80) + 0.4*minmax(turnovers_won_per80)
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Poids directs par métrique et par poste (somme = 1.0 pour chaque poste).
# Discipline retirée du score → appliquée en malus après calcul du rating.
# ---------------------------------------------------------------------------

NAIM_POS_WEIGHTS: dict[str, dict[str, float]] = {
    "FRONT_ROW": {
        "tackles_per80":       0.35,
        "turnovers_won_per80": 0.20,
        "line_breaks_per80":   0.05,
        "offloads_per80":      0.10,
        "tries_per80":         0.05,
        "weight_kg":           0.25,
    },
    "LOCK": {
        "tackles_per80":       0.40,
        "turnovers_won_per80": 0.20,
        "line_breaks_per80":   0.05,
        "offloads_per80":      0.10,
        "tries_per80":         0.05,
        "height_cm":           0.20,
    },
    "BACK_ROW": {
        "tackles_per80":       0.30,
        "turnovers_won_per80": 0.30,
        "line_breaks_per80":   0.05,
        "offloads_per80":      0.15,
        "tries_per80":         0.10,
        "weight_kg":           0.10,
    },
    "SCRUM_HALF": {
        "tackles_per80":       0.15,
        "turnovers_won_per80": 0.20,
        "line_breaks_per80":   0.10,
        "offloads_per80":      0.40,
        "kick_points_per80":   0.05,
        "tries_per80":         0.10,
    },
    "FLY_HALF": {
        "tackles_per80":       0.10,
        "turnovers_won_per80": 0.15,
        "line_breaks_per80":   0.20,
        "offloads_per80":      0.25,
        "kick_points_per80":   0.15,
        "tries_per80":         0.15,
    },
    "WINGER": {
        "tackles_per80":       0.10,
        "turnovers_won_per80": 0.10,
        "line_breaks_per80":   0.40,
        "offloads_per80":      0.15,
        "kick_points_per80":   0.05,
        "tries_per80":         0.15,
        "weight_kg":           0.05,
    },
    "CENTRE": {
        "tackles_per80":       0.20,
        "turnovers_won_per80": 0.15,
        "line_breaks_per80":   0.25,
        "offloads_per80":      0.20,
        "tries_per80":         0.10,
        "weight_kg":           0.10,
    },
    "FULLBACK": {
        "tackles_per80":       0.15,
        "turnovers_won_per80": 0.10,
        "line_breaks_per80":   0.25,
        "offloads_per80":      0.15,
        "kick_points_per80":   0.20,
        "tries_per80":         0.15,
    },
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

# ---------------------------------------------------------------------------
# Corrections de poste — joueurs mal classifiés par LNR (groupe trop large).
# Clé : sous-chaîne du lnr_slug (insensible à la casse).
# Valeur : position_group corrigée.
# ---------------------------------------------------------------------------
POSITION_OVERRIDES: dict[str, str] = {
    "louis-bielle-biarrey": "WINGER",   # classifié FULLBACK par LNR, joue ailier
    "james-thomas-ritchie": "BACK_ROW", # classifié LOCK par LNR, flanker de métier
}

# Pour get_rating_breakdown (rétrocompatibilité)
POS_WEIGHTS = {pg: {"metrics": {}, "w_disc": 0.0} for pg in NAIM_POS_WEIGHTS}


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
    """Retourne la colonne comme float, rempli par 0 si absente ou NaN."""
    if col not in group.columns:
        return np.zeros(len(group), dtype=float)
    s = group[col].fillna(0.0)
    return s.values.astype(float)


# ---------------------------------------------------------------------------
# Discipline malus — appliqué APRÈS le rating
# ---------------------------------------------------------------------------

def _discipline_malus(row) -> float:
    """
    Malus cartons appliqué après calcul du rating.
    YC: -2pts | OC: -3pts | RC: -8pts | cap: -10pts total.
    """
    yc = float(row.get("yellow_cards", 0) or 0)
    oc = float(row.get("orange_cards", 0) or 0)
    rc = float(row.get("red_cards", 0) or 0)
    malus = yc * 2.0 + oc * 3.0 + rc * 8.0
    return min(malus, 10.0)


# ---------------------------------------------------------------------------
# Confiance — step function avec floor à 0.50
# ---------------------------------------------------------------------------

def _confidence_v2(minutes: float, _p90: float = 0.0) -> float:
    """
    Step function — plus d'utilisation de p90 (trop variable par poste).
    Floor à 0.50 : un joueur avec peu de matchs est toujours partiellement
    récompensé pour sa performance, pas réduit à la moyenne absolue.
    """
    if minutes >= 600:
        return 1.00
    elif minutes >= 300:
        return 0.75
    elif minutes >= 150:
        return 0.60
    else:
        return 0.50


# ---------------------------------------------------------------------------
# Calcul principal — Architecture v6
# ---------------------------------------------------------------------------

def calculate_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Poids directs par métrique et par poste.
    Discipline = malus post-calcul.
    Confiance = step function (floor 0.50).
    """
    df = df.copy()

    # Appliquer les corrections de poste (POSITION_OVERRIDES)
    if "lnr_slug" in df.columns:
        for slug_key, corrected_pos in POSITION_OVERRIDES.items():
            mask = df["lnr_slug"].str.lower() == slug_key
            if mask.any():
                df.loc[mask, "position_group"] = corrected_pos
                print(f"[OVERRIDE] {slug_key} -> {corrected_pos} ({mask.sum()} joueur(s))")

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
        # 1. Calcul kick_points_per80 si nécessaire
        # ----------------------------------------------------------------
        if "kick_points_per80" in pos_w:
            pts  = _get_col(group, "points_scored_per80")
            tries = _get_col(group, "tries_per80")
            group["kick_points_per80"] = np.maximum(pts - tries * 5.0, 0.0)

        # ----------------------------------------------------------------
        # 2. Normalisation min-max [p5, p95] par poste pour chaque métrique
        # ----------------------------------------------------------------
        normed: dict[str, np.ndarray] = {}
        for metric in pos_w:
            raw = _get_col(group, metric)
            normed[metric] = _minmax(raw)

        # ----------------------------------------------------------------
        # 3. Score pondéré (poids somment à 1.0 → score_raw ∈ [0, 100])
        # ----------------------------------------------------------------
        score_raw = np.zeros(len(group), dtype=float)
        for metric, w in pos_w.items():
            score_raw += w * normed[metric]

        # ----------------------------------------------------------------
        # 4. Confiance (step function)
        # ----------------------------------------------------------------
        conf = np.array([_confidence_v2(m) for m in mt])

        # ----------------------------------------------------------------
        # 5. Shrinkage vers 50 selon confiance
        # ----------------------------------------------------------------
        score_final = conf * score_raw + (1.0 - conf) * 50.0

        # ----------------------------------------------------------------
        # 6. Rating FIFA → [40, 99]
        # ----------------------------------------------------------------
        group["rating_raw"] = np.round(np.clip(40.0 + 0.6 * score_raw,   40.0, 99.0), 1)
        group["rating"]     = np.round(np.clip(40.0 + 0.6 * score_final, 40.0, 99.0), 1)
        group["confidence"] = np.round(conf, 3)

        # ----------------------------------------------------------------
        # 7. Axes visuels [0, 100] — indépendants du scoring
        # ----------------------------------------------------------------
        lb    = _minmax(_get_col(group, "line_breaks_per80"))
        off   = _minmax(_get_col(group, "offloads_per80"))
        tack  = _minmax(_get_col(group, "tackles_per80"))
        tow   = _minmax(_get_col(group, "turnovers_won_per80"))
        tries = _minmax(_get_col(group, "tries_per80"))

        if "kick_points_per80" in group.columns:
            kick_ui = _minmax(_get_col(group, "kick_points_per80"))
        else:
            kick_ui = _minmax(_get_col(group, "points_scored_per80"))

        group["axis_att"]  = np.round(lb).astype(int)
        group["axis_ctrl"] = np.round(off).astype(int)
        group["axis_kick"] = np.round(kick_ui).astype(int)
        group["axis_def"]  = np.round(tack).astype(int)
        group["axis_pow"]  = np.round(0.6 * tries + 0.4 * tow).astype(int)

        # Gabarit (composante physique brute — pour affichage carte)
        if pg == "FRONT_ROW":
            weight_raw = _get_col(group, "weight_kg")
            gabarit = _minmax(weight_raw) if weight_raw.sum() > 0 else np.zeros(len(group))
        elif pg == "LOCK":
            height_raw = _get_col(group, "height_cm")
            gabarit = _minmax(height_raw) if height_raw.sum() > 0 else np.zeros(len(group))
        else:
            gabarit = np.zeros(len(group), dtype=float)
        group["axis_gabarit"] = np.round(np.clip(gabarit, 0.0, 100.0)).astype(int)

        result_parts.append(group)

    combined = pd.concat(result_parts).sort_index()

    # ----------------------------------------------------------------
    # 8. Discipline malus (appliqué sur le rating final)
    # ----------------------------------------------------------------
    malus = combined.apply(_discipline_malus, axis=1)
    combined["rating"]     = (combined["rating"]     - malus).clip(lower=40.0).round(1)
    combined["rating_raw"] = (combined["rating_raw"] - malus).clip(lower=40.0).round(1)

    # axis_disc : visuel discipline (100=clean, 0=max cartons)
    combined["axis_disc"] = (100.0 - malus * 10.0).clip(lower=0.0).astype(int)

    # ----------------------------------------------------------------
    # 9. Métadonnées UI
    # ----------------------------------------------------------------
    combined["position_label"] = combined["position_group"].map(POSITION_GROUP_LABEL)
    combined["position_abbr"]  = combined["position_group"].map(POSITION_ABBR)

    combined["confidence_score"] = (combined["confidence"] * 100).round(0).clip(upper=100).fillna(50).astype(int)

    def _conf_badge(c: float) -> str:
        if c >= 0.75: return "Haute"
        if c >= 0.60: return "Moyenne"
        return "Basse"
    combined["confidence_badge"] = combined["confidence"].apply(_conf_badge)
    combined["low_sample"]       = combined["confidence"] < 0.75

    if "matches_played" in combined.columns and "minutes_avg" in combined.columns:
        mt_ui = combined["matches_played"].fillna(0) * combined["minutes_avg"].fillna(0)
        combined["minutes_bucket"] = mt_ui.apply(_minutes_bucket)
    else:
        combined["minutes_bucket"] = "Basse"

    mp_col = "matches_played"
    if mp_col in combined.columns:
        combined["data_insufficient"] = (
            (combined[mp_col].fillna(0) < 5) | (combined["confidence"] < 0.60)
        )
    else:
        combined["data_insufficient"] = combined["confidence"] < 0.60

    combined["rank_position"] = combined.groupby("position_group")["rating"].rank(
        ascending=False, method="min"
    ).fillna(999).astype(int)

    combined["rating_percentile_position"] = combined.groupby("position_group")["rating"].transform(
        lambda s: s.rank(pct=True) * 100
    ).round(1)

    # Enrichissement données internationales (Naim)
    try:
        from engine.merge_intl import enrich_with_intl
        combined = enrich_with_intl(combined)
    except Exception as e:
        print(f"[MERGE] Enrichissement intl ignoré : {e}")

    return combined


# ---------------------------------------------------------------------------
# Breakdown explicatif (pour page Player Cards)
# ---------------------------------------------------------------------------

def get_rating_breakdown(player_row: pd.Series) -> list[dict]:
    """
    Retourne la contribution de chaque métrique pour ce joueur.
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
            "pct":     None,
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

    s_rank = {s: i for i, s in enumerate(_POST_COVID_SEASONS)}
    hist["_rank"] = hist["season"].map(s_rank).fillna(-1)

    hist["_key"] = hist["name"].str.strip().str.lower()
    prior_map: dict[str, float] = {}
    for key, grp in hist.groupby("_key"):
        recent  = grp.nlargest(n_prior, "_rank").sort_values("_rank")
        w       = np.arange(1, len(recent) + 1, dtype=float)
        prior_map[key] = round(float(np.average(recent["rating"].values, weights=w)), 1)

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

    # display_rating : pour les joueurs avec peu de minutes (<300),
    # utiliser rating_value (blend historique) plutôt que rating saison pure.
    if "minutes_total" in df.columns:
        mt_col = df["minutes_total"].fillna(0)
    else:
        mt_col = (df["matches_played"].fillna(0) * df["minutes_avg"].fillna(0))

    df["display_rating"] = df.apply(
        lambda r: r["rating_value"] if mt_col.loc[r.name] < 300 and r.get("has_prior", False) else r["rating"],
        axis=1,
    ).round(1)

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
