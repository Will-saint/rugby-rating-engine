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
        "tackles_per80":       0.30,   # 0.40→0.30 : volume pur ne doit pas dominer
        "turnovers_won_per80": 0.25,   # 0.20→0.25 : grattage = compétence différenciante
        "line_breaks_per80":   0.10,   # 0.05→0.10 : 2e ligne mobile valorisé
        "offloads_per80":      0.15,   # 0.10→0.15 : offload = compétence 2e ligne moderne
        "tries_per80":         0.10,   # 0.05→0.10 : contribution offensive
        "height_cm":           0.10,   # 0.20→0.10 : taille physique, moins déterminante
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
        "tackles_per80":       0.10,
        "turnovers_won_per80": 0.20,
        "line_breaks_per80":   0.10,
        "offloads_per80":      0.25,
        "kick_points_per80":   0.05,
        "tries_per80":         0.15,
        "passes_per80":        0.10,   # distribution — bonus seulement (paywall)
        "weight_kg":           0.05,
    },
    "FLY_HALF": {
        "tackles_per80":       0.12,
        "turnovers_won_per80": 0.05,   # stat aléatoire pour un 10 — réduit de 0.15
        "line_breaks_per80":   0.20,   # franchissement = indicateur clé 10 attaquant
        "offloads_per80":      0.18,   # moins critique que pour un 9 — réduit de 0.25
        "kick_points_per80":   0.20,   # compétence primaire d'un 10
        "tries_per80":         0.20,   # contribution offensive directe
        "height_cm":           0.05,
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
        "line_breaks_per80":   0.20,   # -0.05 pour laisser place au gabarit
        "offloads_per80":      0.15,
        "kick_points_per80":   0.20,
        "tries_per80":         0.15,
        "height_cm":           0.05,   # hauteur = up-and-under, ballons hauts
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
    "arthur-retiere":        "WINGER",  # classifié SCRUM_HALF par LNR, joue ailier/arrière
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

# ---------------------------------------------------------------------------
# Courbe d'âge — bonus/malus en points de rating
# Gaussienne centrée sur 28.5 ans (pic biologique du rugbyman professionnel).
#   Peak (28.5 ans) : +3.0 pts
#   24 ans          : +0.5 pts  (talent en éclosion)
#   22 ans          : -0.7 pts  (encore en développement)
#   34 ans          : -0.2 pts  (encore compétitif)
#   36+ ans         : -1.0 pts  (déclin progressif)
# ---------------------------------------------------------------------------

_AGE_PEAK  = 28.5
_AGE_SIGMA = 5.0
_AGE_AMP   = 4.5   # amplitude gaussienne (pic = AMP - OFFSET)
_AGE_OFF   = 1.5   # décalage vertical (minimum théorique = -OFFSET)
_AGE_MAX   = 3.0   # cap bonus
_AGE_MIN   = -3.0  # cap malus


def _age_factor(age) -> float:
    """
    Retourne le bonus/malus d'âge en points de rating.
    0.0 si âge non disponible.
    """
    try:
        a = float(age)
        if np.isnan(a) or a < 14 or a > 50:
            return 0.0
    except (TypeError, ValueError):
        return 0.0
    raw = _AGE_AMP * np.exp(-((a - _AGE_PEAK) / _AGE_SIGMA) ** 2) - _AGE_OFF
    return float(np.clip(raw, _AGE_MIN, _AGE_MAX))


# Métriques "bonus seulement" par poste.
# Plancher à 50 (médiane) → ne pénalise pas les non-spécialistes,
# mais récompense ceux qui excellent dans ce domaine.
# Règle : kick_points_per80 est optionnel pour 9, ailier, 3L, centre.
#          Pour 10 et arrière, taper fait partie du poste → reste normal.
_BONUS_METRICS: dict[str, frozenset] = {
    "SCRUM_HALF": frozenset({"kick_points_per80", "passes_per80"}),
    "WINGER":     frozenset({"kick_points_per80"}),
    "BACK_ROW":   frozenset({"kick_points_per80"}),
    "CENTRE":     frozenset({"kick_points_per80"}),
}

# Blend gabarit par poste : (poids_height, poids_weight)
# Reflète l'importance relative de la taille vs du poids selon le rôle.
_GABARIT_BLEND: dict[str, tuple[float, float]] = {
    "FRONT_ROW":  (0.20, 0.80),  # piliers/talonneur → masse prime
    "LOCK":       (0.85, 0.15),  # 2ème ligne → taille prime
    "BACK_ROW":   (0.35, 0.65),  # flankers/n°8 → puissance + mobilité
    "SCRUM_HALF": (0.40, 0.60),  # explosivité, impact aux rucks
    "FLY_HALF":   (0.65, 0.35),  # vision en l'air, portée de pied
    "WINGER":     (0.35, 0.65),  # vitesse + puissance de percée
    "CENTRE":     (0.30, 0.70),  # puissance de franchissement
    "FULLBACK":   (0.65, 0.35),  # ballons hauts, jeu au pied
}


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
    Interpolation linéaire par segments (remplace la step function).
    Élimine les discontinuités à 150 / 300 / 600 min qui créaient des
    sauts artificiels de note pour des joueurs très proches en temps de jeu.

    Paliers d'ancrage :
      0 min  → 0.50 (floor absolu)
      150 min → 0.60
      300 min → 0.75
      600 min → 1.00

    Entre deux paliers : interpolation linéaire.
    """
    ANCHORS = [(0, 0.50), (150, 0.60), (300, 0.75), (600, 1.00)]
    minutes = max(0.0, float(minutes))
    if minutes >= 600:
        return 1.00
    for (m0, c0), (m1, c1) in zip(ANCHORS, ANCHORS[1:]):
        if minutes <= m1:
            t = (minutes - m0) / (m1 - m0)
            return round(c0 + t * (c1 - c0), 4)
    return 1.00


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

    # Normalisation globale taille/poids (toutes positions confondues)
    # Utilisée pour le blend axis_gabarit : 70 % intra-poste + 30 % global.
    # → un 9 de 175 cm garde un bon score parmi ses pairs mais reste
    #   clairement en-dessous d'un prop de 135 kg sur l'échelle absolue.
    _h_all = _get_col(df, "height_cm")
    _w_all = _get_col(df, "weight_kg")
    _h_global = _minmax(_h_all) if _h_all.sum() > 0 else np.full(len(df), 50.0)
    _w_global = _minmax(_w_all) if _w_all.sum() > 0 else np.full(len(df), 50.0)
    df["_h_global_norm"] = _h_global
    df["_w_global_norm"] = _w_global

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
        #    Métriques "bonus" : plancher à 50 → ne pénalise pas les
        #    non-spécialistes, récompense ceux qui excellent.
        # ----------------------------------------------------------------
        bonus_set = _BONUS_METRICS.get(pg, frozenset())
        normed: dict[str, np.ndarray] = {}
        for metric in pos_w:
            raw = _get_col(group, metric)
            normed_arr = _minmax(raw)
            if metric in bonus_set:
                normed_arr = np.maximum(normed_arr, 50.0)   # bonus-only
            normed[metric] = normed_arr

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
        # 7. Axes visuels [0, 95] — indépendants du scoring
        #    Normalisation [p10, p90] (plus douce que p5/p95) pour éviter
        #    la saturation des extrêmes. Clip max à 95 pour garder une marge.
        #    KICK : floor à 5 pour éviter l'effet "0 absolu" sur les non-tapeurs.
        # ----------------------------------------------------------------
        _ui = lambda arr: np.clip(_minmax(arr, p_low=10.0, p_high=90.0), 0.0, 95.0)
        lb    = _ui(_get_col(group, "line_breaks_per80"))
        off   = _ui(_get_col(group, "offloads_per80"))
        tack  = _ui(_get_col(group, "tackles_per80"))
        tow   = _ui(_get_col(group, "turnovers_won_per80"))
        tries = _ui(_get_col(group, "tries_per80"))

        if "kick_points_per80" in group.columns:
            kick_ui = _ui(_get_col(group, "kick_points_per80"))
        else:
            kick_ui = _ui(_get_col(group, "points_scored_per80"))
        kick_ui = np.maximum(kick_ui, 5.0)  # floor 5 : jamais "0 absolu" pour KICK

        group["axis_att"]  = np.round(lb).astype(int)
        group["axis_ctrl"] = np.round(off).astype(int)
        group["axis_kick"] = np.round(kick_ui).astype(int)
        group["axis_def"]  = np.round(tack).astype(int)
        group["axis_pow"]  = np.round(np.clip(0.6 * tries + 0.4 * tow, 0.0, 95.0)).astype(int)

        # Gabarit — blend taille/poids selon le rôle
        # axis_gabarit = 70 % intra-poste + 30 % global
        #   → récompense le joueur physiquement fort pour son poste
        #   → mais plafonne le score si le gabarit absolu est faible
        #   Ex : Dupont (175/85, excellent 9) ≈ 58  |  Atonio (196/145, prop massif) ≈ 98
        wh, ww = _GABARIT_BLEND.get(pg, (0.5, 0.5))
        h_raw  = _get_col(group, "height_cm")
        w_raw  = _get_col(group, "weight_kg")
        h_pos  = _minmax(h_raw) if h_raw.sum() > 0 else np.full(len(group), 50.0)
        w_pos  = _minmax(w_raw) if w_raw.sum() > 0 else np.full(len(group), 50.0)
        h_glob = group["_h_global_norm"].values
        w_glob = group["_w_global_norm"].values
        # 70 % position + 30 % global
        h_blend = 0.70 * h_pos + 0.30 * h_glob
        w_blend = 0.70 * w_pos + 0.30 * w_glob
        gabarit = wh * h_blend + ww * w_blend
        group["axis_gabarit"] = np.round(np.clip(gabarit, 0.0, 100.0)).astype(int)

        result_parts.append(group)

    combined = pd.concat(result_parts).sort_index()

    # ----------------------------------------------------------------
    # 7b. Form weighting — blend score_saison × score_forme récente
    #     Poids : 80% saison + 20% forme (5 derniers matchs, decay 0.7)
    # ----------------------------------------------------------------
    try:
        from engine.form import get_form_df
        form_df = get_form_df()
        if not form_df.empty and "lnr_slug" in combined.columns:
            combined = combined.merge(
                form_df[["lnr_slug", "form_score", "form_trend", "form_matches", "form_scores_list"]],
                on="lnr_slug", how="left",
            )
            has_form = combined["form_score"].notna()
            # Blend uniquement pour les joueurs avec données de forme
            combined.loc[has_form, "rating"] = (
                0.80 * combined.loc[has_form, "rating"] +
                0.20 * combined.loc[has_form, "form_score"]
                        .map(lambda fs: 40.0 + 0.6 * fs)  # convertir [0,100] → échelle FIFA
            ).clip(40, 99).round(1)
            # Remplir les joueurs sans forme (pas de matchs récents)
            combined["form_score"]       = combined["form_score"].fillna(50.0)
            combined["form_trend"]       = combined["form_trend"].fillna("→")
            combined["form_matches"]     = combined["form_matches"].fillna(0).astype(int)
            combined["form_scores_list"] = combined["form_scores_list"].apply(
                lambda x: x if isinstance(x, list) else []
            )
            n_form = int(has_form.sum())
            print(f"[FORM] Blend forme appliqué sur {n_form} joueurs")
        else:
            combined["form_score"]       = 50.0
            combined["form_trend"]       = "→"
            combined["form_matches"]     = 0
            combined["form_scores_list"] = [[] for _ in range(len(combined))]
    except Exception as e:
        print(f"[FORM] Ignoré : {e}")
        combined["form_score"]       = 50.0
        combined["form_trend"]       = "→"
        combined["form_matches"]     = 0
        combined["form_scores_list"] = [[] for _ in range(len(combined))]

    # ----------------------------------------------------------------
    # 8. Discipline malus (appliqué sur le rating final)
    # ----------------------------------------------------------------
    malus = combined.apply(_discipline_malus, axis=1)
    combined["rating"]     = (combined["rating"]     - malus).clip(lower=40.0).round(1)
    combined["rating_raw"] = (combined["rating_raw"] - malus).clip(lower=40.0).round(1)

    # axis_disc : visuel discipline (100=clean, 0=max cartons)
    combined["axis_disc"] = (100.0 - malus * 10.0).clip(lower=0.0).astype(int)

    # axis_consistency : préservé tel quel depuis player_consistency.csv (injecté avant scoring)
    # Si absent (pas de match history), on default à 50.
    if "axis_consistency" not in combined.columns:
        combined["axis_consistency"] = 50

    # ----------------------------------------------------------------
    # 8.5. Courbe d'âge — bonus/malus post-discipline
    #      Peak +3 pts à 28-29 ans | -0.7 à 22 ans | -1 à 36+ ans
    # ----------------------------------------------------------------
    if "age" in combined.columns:
        age_bonus = combined["age"].apply(_age_factor)
        combined["age_factor"] = age_bonus.round(2)
        combined["rating"]     = (combined["rating"]     + age_bonus).clip(40.0, 99.0).round(1)
        combined["rating_raw"] = (combined["rating_raw"] + age_bonus).clip(40.0, 99.0).round(1)
        n_age = int(combined["age"].notna().sum())
        print(f"[AGE] Courbe d'âge appliquée sur {n_age} joueurs "
              f"(pic +{_AGE_MAX:.0f} pts à {_AGE_PEAK:.0f} ans)")
    else:
        combined["age_factor"] = 0.0

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

    # ----------------------------------------------------------------
    # 10. Ancrage réputation (FIFA-like)
    #     Pour les joueurs avec peu de matchs T14 mais un historique
    #     international fort : on remplace le plancher à 50 par un
    #     plancher basé sur la réputation internationale.
    #     → Jamais une pénalisation, uniquement un boost.
    #     Formule : rating_floor = intl * (0.85 + 0.05 * (1 - conf))
    #       conf=0.50 → floor=90%  intl
    #       conf=0.60 → floor=87%  intl  (Dupont: 93.4*0.87 = 81.3)
    #       conf=0.75 → floor=875% intl
    #       conf=1.00 → pas de boost (joueur avec suffisamment de matchs)
    # ----------------------------------------------------------------
    if "rating_intl" in combined.columns and "confidence" in combined.columns:
        combined["rating_intl"] = pd.to_numeric(combined["rating_intl"], errors="coerce")
        # Appliqué à TOUS les joueurs capés (confidence<1 restriction supprimée).
        # Un joueur full-season avec intl élevé peut être sous-évalué faute de données paywall.
        # conf=1.0 → factor=0.85 | conf=0.5 → factor=0.875 — jamais une pénalisation.
        _rep_mask = combined["rating_intl"].notna()
        if _rep_mask.any():
            _conf_r     = combined.loc[_rep_mask, "confidence"].astype(float)
            _rep_factor = 0.85 + 0.05 * (1.0 - _conf_r)
            _rep_floor  = combined.loc[_rep_mask, "rating_intl"].astype(float) * _rep_factor
            _current    = combined.loc[_rep_mask, "rating"].astype(float)
            combined.loc[_rep_mask, "rating"] = (
                np.maximum(_current.values, _rep_floor.values)
                .clip(40.0, 99.0)
                .round(1)
            )
            n_rep = int((_rep_floor > _current).sum())
            print(f"[REPUTATION] Plancher réputation intl appliqué sur {n_rep} joueurs")

    # ----------------------------------------------------------------
    # 11. Bonus international — récompense le niveau intl (notes Naim)
    #     Appliqué à TOUS les joueurs capés, pas seulement basse confiance.
    #     Max +2.5 pts pour un joueur noté 100 internationalement.
    #     Seuil à 75 : pas de bonus en-dessous (joueurs moyens à l'intl).
    #     Formule : bonus = ((intl - 75) / 25) * 2.5, clipé [0, 2.5]
    #       intl=100 → +2.5 pts | intl=90 → +1.5 pts | intl=75 → +0 pt
    # ----------------------------------------------------------------
    if "rating_intl" in combined.columns:
        combined["rating_intl"] = pd.to_numeric(combined["rating_intl"], errors="coerce")
        _intl_mask = combined["rating_intl"].notna()
        if _intl_mask.any():
            _intl_r    = combined.loc[_intl_mask, "rating_intl"].astype(float)
            _intl_bonus = ((_intl_r - 75.0) / 25.0 * 2.5).clip(0.0, 2.5)
            combined.loc[_intl_mask, "rating"] = (
                combined.loc[_intl_mask, "rating"].astype(float) + _intl_bonus
            ).clip(40.0, 99.0).round(1)
            combined["intl_bonus"] = 0.0
            combined.loc[_intl_mask, "intl_bonus"] = _intl_bonus.values
            n_intl = int(_intl_mask.sum())
            print(f"[INTL BONUS] Bonus international sur {n_intl} joueurs (max +2.5 pts)")
        else:
            combined["intl_bonus"] = 0.0
    else:
        combined["intl_bonus"] = 0.0

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

    # ----------------------------------------------------------------
    # Bonus international : blend display_rating × rating_intl
    # Pour les joueurs avec >= 5 sélections et rating_intl disponible.
    # intl_weight = min(matches_intl / 50, 0.25) → max 25% d'influence intl.
    # La performance en club reste dominante (min 75%).
    # ----------------------------------------------------------------
    if "rating_intl" in df.columns and "matches_intl" in df.columns:
        def _apply_intl_bonus(row) -> float:
            ri = row.get("rating_intl")
            mi = row.get("matches_intl")
            if ri is None or pd.isna(ri):
                return row["display_rating"]
            try:
                mi = float(mi)
            except (TypeError, ValueError):
                return row["display_rating"]
            if mi < 5:
                return row["display_rating"]
            intl_w = min(mi / 50.0, 0.25)
            blended = (1.0 - intl_w) * row["display_rating"] + intl_w * float(ri)
            # Bonus only — never penalize a player for having lower intl rating
            return round(max(row["display_rating"], blended), 1)

        df["display_rating"] = df.apply(_apply_intl_bonus, axis=1)
        n_bonus = (df["matches_intl"].fillna(0) >= 5).sum()
        print(f"[INTL_BONUS] Appliqué sur {n_bonus} joueurs (>= 5 sélections)")

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
