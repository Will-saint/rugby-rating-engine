"""
Rugby Rating Engine v3 — Z-score par poste.

Pipeline :
  1. Z-score chaque métrique dans le poste (clip ±3).
  2. Discipline : P = 0.6·YC + 1.2·OC + 2.0·RC → Z-scoré dans le poste.
  3. score_raw = clip(50 + 10 · S_pos, 0, 100)
       où S_pos = Σ w_m · Z_m  −  w_disc · Z_P
  4. Fiabilité : conf = clip(minutes_total / p90_minutes_pos, 0, 1)
  5. score_final = conf · score_raw + (1 − conf) · 50
  6. rating = clip(40 + 0.6 · score_final, 40, 99)
  7. 6 axes visuels (Z-scores intra-poste → 0–100)

Seules les métriques disponibles dans les données LNR publiques sont utilisées :
  TACK  = tackles_per80        (100 % coverage)
  LB    = line_breaks_per80    (100 % coverage)
  OFF   = offloads_per80       (100 % coverage)
  TOw   = turnovers_won_per80  (100 % coverage)
  PTS   = points_scored_per80  (100 % coverage)
  Disc  = yellow/orange/red_cards  (via P score)
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Pondérations par poste
# Les poids somment à 1.0 (hors discipline).
# w_disc est le coefficient du malus discipline dans S_pos.
# ---------------------------------------------------------------------------

POS_WEIGHTS: dict[str, dict] = {
    "FRONT_ROW": {
        "metrics": {
            "tackles_per80":       0.50,
            "turnovers_won_per80": 0.30,
            "offloads_per80":      0.15,
            "points_scored_per80": 0.05,
        },
        "w_disc": 0.20,
    },
    "LOCK": {
        "metrics": {
            "tackles_per80":       0.55,
            "turnovers_won_per80": 0.25,
            "points_scored_per80": 0.10,
            "offloads_per80":      0.10,
        },
        "w_disc": 0.20,
    },
    "BACK_ROW": {
        "metrics": {
            "turnovers_won_per80": 0.35,
            "tackles_per80":       0.30,
            "offloads_per80":      0.15,
            "line_breaks_per80":   0.10,
            "points_scored_per80": 0.10,
        },
        "w_disc": 0.20,
    },
    "SCRUM_HALF": {
        "metrics": {
            "offloads_per80":      0.30,
            "line_breaks_per80":   0.25,
            "points_scored_per80": 0.20,
            "tackles_per80":       0.15,
            "turnovers_won_per80": 0.10,
        },
        "w_disc": 0.20,
    },
    "FLY_HALF": {
        "metrics": {
            "points_scored_per80": 0.45,
            "line_breaks_per80":   0.20,
            "offloads_per80":      0.15,
            "tackles_per80":       0.10,
            "turnovers_won_per80": 0.10,
        },
        "w_disc": 0.25,
    },
    "WINGER": {
        "metrics": {
            "line_breaks_per80":   0.45,
            "points_scored_per80": 0.30,
            "offloads_per80":      0.20,
            "tackles_per80":       0.05,
        },
        "w_disc": 0.15,
    },
    "CENTRE": {
        "metrics": {
            "line_breaks_per80":   0.30,
            "offloads_per80":      0.25,
            "tackles_per80":       0.25,
            "points_scored_per80": 0.15,
            "turnovers_won_per80": 0.05,
        },
        "w_disc": 0.20,
    },
    "FULLBACK": {
        "metrics": {
            "line_breaks_per80":   0.35,
            "points_scored_per80": 0.30,
            "offloads_per80":      0.20,
            "tackles_per80":       0.10,
            "turnovers_won_per80": 0.05,
        },
        "w_disc": 0.20,
    },
}

# ---------------------------------------------------------------------------
# 6 Axes visuels — métriques par poste
# Chaque axe est la moyenne des Z-scores des métriques listées → mappé en 0-100
# ---------------------------------------------------------------------------

AXES_METRICS: dict[str, dict[str, list[str]]] = {
    "att": {  # Ball Carry — activité balle en main
        "FRONT_ROW":  ["offloads_per80"],
        "LOCK":       ["offloads_per80", "line_breaks_per80"],
        "BACK_ROW":   ["offloads_per80", "line_breaks_per80"],
        "SCRUM_HALF": ["line_breaks_per80", "offloads_per80"],
        "FLY_HALF":   ["line_breaks_per80", "offloads_per80"],
        "WINGER":     ["line_breaks_per80", "offloads_per80"],
        "CENTRE":     ["line_breaks_per80", "offloads_per80"],
        "FULLBACK":   ["line_breaks_per80", "offloads_per80"],
    },
    "def": {  # Defense — plaquages
        pg: ["tackles_per80"] for pg in POS_WEIGHTS
    },
    "disc": {  # Discipline — inversé : Z_P négatif = discipliné
        pg: ["_disc_score"] for pg in POS_WEIGHTS  # colonne temporaire
    },
    "ctrl": {  # Breakdown / contrôle
        "FRONT_ROW":  ["turnovers_won_per80"],
        "LOCK":       ["turnovers_won_per80"],
        "BACK_ROW":   ["turnovers_won_per80"],
        "SCRUM_HALF": ["turnovers_won_per80", "offloads_per80"],
        "FLY_HALF":   ["turnovers_won_per80"],
        "WINGER":     ["turnovers_won_per80"],
        "CENTRE":     ["turnovers_won_per80", "offloads_per80"],
        "FULLBACK":   ["turnovers_won_per80"],
    },
    "kick": {  # Kicking / impact offensif — proxy via points
        pg: ["points_scored_per80"] for pg in POS_WEIGHTS
    },
    "pow": {  # Set Piece / puissance
        "FRONT_ROW":  ["tackles_per80", "turnovers_won_per80"],
        "LOCK":       ["tackles_per80", "turnovers_won_per80"],
        "BACK_ROW":   ["tackles_per80", "turnovers_won_per80", "offloads_per80"],
        "SCRUM_HALF": ["tackles_per80"],
        "FLY_HALF":   ["tackles_per80"],
        "WINGER":     ["line_breaks_per80"],
        "CENTRE":     ["tackles_per80"],
        "FULLBACK":   ["tackles_per80"],
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
# Helpers
# ---------------------------------------------------------------------------

def _zscore(values: np.ndarray, clip: float = 3.0) -> np.ndarray:
    """Z-score d'un vecteur, clipé à ±clip. Retourne 0 si std=0."""
    mu, sigma = values.mean(), values.std()
    if sigma < 1e-9:
        return np.zeros_like(values, dtype=float)
    return np.clip((values - mu) / sigma, -clip, clip)


def _minutes_bucket(m: float) -> str:
    if m >= 1400: return "Haute"
    if m >= 800:  return "Bonne"
    if m >= 400:  return "Moyenne"
    return "Basse"


# ---------------------------------------------------------------------------
# Calcul principal
# ---------------------------------------------------------------------------

def calculate_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Entrée  : DataFrame players (colonnes stats per80 + cartes + minutes)
    Sortie  : même DataFrame + rating, rating_raw, axis_*, confidence_score,
              confidence_badge, low_sample, data_insufficient, rank_position,
              rating_percentile_position, minutes_bucket
    """
    result_parts = []

    for pg, cfg in POS_WEIGHTS.items():
        group = df[df["position_group"] == pg].copy()
        if group.empty:
            continue

        w_metrics = cfg["metrics"]
        w_disc    = cfg["w_disc"]

        # ----------------------------------------------------------------
        # 0. Minutes totales
        # ----------------------------------------------------------------
        if "minutes_total" in group.columns:
            mt = group["minutes_total"].fillna(0).values.astype(float)
        else:
            mt = (
                group["matches_played"].fillna(0) *
                group["minutes_avg"].fillna(0)
            ).values.astype(float)

        # ----------------------------------------------------------------
        # 1. Score discipline per80 = (0.6·YC + 1.2·OC + 2.0·RC) / min_total * 80
        #    Normalise par le temps joué → comparable entre joueurs
        # ----------------------------------------------------------------
        yc = group["yellow_cards"].fillna(0).values.astype(float) if "yellow_cards" in group.columns else np.zeros(len(group))
        oc = group["orange_cards"].fillna(0).values.astype(float) if "orange_cards" in group.columns else np.zeros(len(group))
        rc = group["red_cards"].fillna(0).values.astype(float)    if "red_cards"    in group.columns else np.zeros(len(group))
        disc_total = 0.6 * yc + 1.2 * oc + 2.0 * rc
        disc_raw   = np.where(mt > 0, disc_total / mt * 80, 0.0)  # cartons /80 min
        z_disc     = _zscore(disc_raw)   # haut = beaucoup de cartes = mauvais
        group["_disc_score"] = disc_raw  # pour axe visuel

        # ----------------------------------------------------------------
        # 2. Z-scores des métriques + score_raw
        # ----------------------------------------------------------------
        z_matrix = {}
        for metric in w_metrics:
            if metric not in group.columns:
                z_matrix[metric] = np.zeros(len(group))
                continue
            vals = group[metric].fillna(group[metric].median()).values.astype(float)
            z_matrix[metric] = _zscore(vals)

        # S_pos = Σ w_m · Z_m  −  w_disc · Z_P
        S = sum(w * z_matrix[m] for m, w in w_metrics.items()) - w_disc * z_disc
        score_raw = np.clip(50.0 + 10.0 * S, 0.0, 100.0)

        # ----------------------------------------------------------------
        # 3. Fiabilité conf = clip(min_total / p90_min_pos, 0, 1)
        # ----------------------------------------------------------------
        p90 = float(np.percentile(mt[mt > 0], 90)) if (mt > 0).sum() >= 5 else 1200.0
        p90 = max(p90, 400.0)
        conf = np.clip(mt / p90, 0.0, 1.0)

        # ----------------------------------------------------------------
        # 4. score_final avec shrinkage vers 50 (FIFA neutre)
        # ----------------------------------------------------------------
        score_final = conf * score_raw + (1.0 - conf) * 50.0

        # ----------------------------------------------------------------
        # 5. rating FIFA : 40 + 0.6 · score_final  →  [40, 99]
        # ----------------------------------------------------------------
        rating_raw  = np.round(np.clip(40.0 + 0.6 * score_raw,   40.0, 99.0), 1)
        rating      = np.round(np.clip(40.0 + 0.6 * score_final, 40.0, 99.0), 1)

        group["rating_raw"]  = rating_raw
        group["rating"]      = rating
        group["confidence"]  = np.round(conf, 3)

        result_parts.append(group)

    combined = pd.concat(result_parts).sort_index()

    # ----------------------------------------------------------------
    # 6. Axes visuels  (Z-score intra-poste → 0-100)
    # ----------------------------------------------------------------
    for axis_name, metrics_by_pos in AXES_METRICS.items():
        axis_vals = pd.Series(50.0, index=combined.index)
        for pg in combined["position_group"].unique():
            grp      = combined[combined["position_group"] == pg]
            metrics  = metrics_by_pos.get(pg, [])
            if not metrics:
                continue

            z_list = []
            for metric in metrics:
                if metric not in grp.columns:
                    continue
                col = grp[metric].fillna(grp[metric].median()).values.astype(float)
                z   = _zscore(col)
                # Pour l'axe discipline : inverser (bas Z_disc = discipliné = bien)
                if axis_name == "disc":
                    z = -z
                z_list.append(z)

            if not z_list:
                continue
            z_mean = np.mean(z_list, axis=0)
            scores = np.round(np.clip(50.0 + 10.0 * z_mean, 0.0, 100.0)).astype(int)
            axis_vals.loc[grp.index] = scores

        combined[f"axis_{axis_name}"] = axis_vals.astype(int)

    # Supprimer la colonne temporaire disc_score
    if "_disc_score" in combined.columns:
        combined.drop(columns=["_disc_score"], inplace=True)

    # ----------------------------------------------------------------
    # 7. Métadonnées UI
    # ----------------------------------------------------------------
    combined["position_label"] = combined["position_group"].map(POSITION_GROUP_LABEL)
    combined["position_abbr"]  = combined["position_group"].map(POSITION_ABBR)

    combined["confidence_score"] = (combined["confidence"] * 100).round(0).clip(upper=100).fillna(50).astype(int)

    def _conf_badge(c: float) -> str:
        if c >= 0.70: return "Haute"
        if c >= 0.40: return "Moyenne"
        return "Basse"
    combined["confidence_badge"] = combined["confidence"].apply(_conf_badge)

    combined["low_sample"] = combined["confidence"] < 0.40

    if "matches_played" in combined.columns and "minutes_avg" in combined.columns:
        mt_calc = combined["matches_played"].fillna(0) * combined["minutes_avg"].fillna(0)
        combined["minutes_bucket"] = mt_calc.apply(_minutes_bucket)
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
