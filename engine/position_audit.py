"""
engine/position_audit.py — Détection automatique des joueurs mal classifiés par poste.

Algorithme :
  Pour chaque joueur, on calcule son score_raw dans TOUS les groupes de poste
  (pas seulement le sien). Si un autre poste produit un score significativement
  plus élevé (> seuil_delta), on génère une suggestion d'override.

  Ce module ne modifie rien — il produit uniquement une liste de suggestions
  affichées dans la page Audit Qualité.

Exemples historiques identifiés :
  - arthur-retiere  : classifié SCRUM_HALF, joue WINGER  (+12.3 pts si WINGER)
  - louis-bielle-biarrey : classifié FULLBACK, joue WINGER (+8.7 pts si WINGER)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from engine.ratings import NAIM_POS_WEIGHTS, POSITION_OVERRIDES, _minmax, _get_col


# Seuil minimal de gain pour suggérer un changement de poste
DELTA_THRESHOLD = 5.0  # points de score_raw (sur 100)


def _compute_score_for_pos(group: pd.DataFrame, pos_w: dict[str, float]) -> np.ndarray:
    """
    Calcule le score_raw de group pour un ensemble de poids pos_w.
    La normalisation est faite sur group (intra-group) — à utiliser avec prudence
    pour les comparaisons cross-postes (indicatif uniquement).
    """
    if "kick_points_per80" in pos_w and "kick_points_per80" not in group.columns:
        pts   = _get_col(group, "points_scored_per80")
        tries = _get_col(group, "tries_per80")
        group = group.copy()
        group["kick_points_per80"] = np.maximum(pts - tries * 5.0, 0.0)

    score = np.zeros(len(group), dtype=float)
    for metric, w in pos_w.items():
        raw    = _get_col(group, metric)
        normed = _minmax(raw)
        score += w * normed
    return score


def detect_position_mismatches(
    df: pd.DataFrame,
    delta_threshold: float = DELTA_THRESHOLD,
    max_suggestions: int = 30,
) -> pd.DataFrame:
    """
    Parcourt tous les joueurs et teste si un poste alternatif donnerait
    un score_raw significativement plus élevé.

    Args:
        df                : DataFrame après calculate_ratings()
        delta_threshold   : gain minimal (score_raw) pour suggérer un override
        max_suggestions   : nombre max de suggestions retournées

    Returns:
        DataFrame trié par gain décroissant avec colonnes :
          lnr_slug, name, team, current_pos, suggested_pos,
          score_current, score_suggested, delta, already_overridden
    """
    if "lnr_slug" not in df.columns or "position_group" not in df.columns:
        return pd.DataFrame()

    # Pré-calcul : score_raw par poste pour chaque joueur
    # On va tester chaque joueur dans chaque poste (cross-poste),
    # en normalisant sur TOUS les joueurs (pas seulement son groupe natif)
    # → approche simplifiée mais suffisante pour détecter les cas extrêmes.

    overridden_slugs = set(POSITION_OVERRIDES.keys())

    rows = []
    for slug, grp in df.groupby("lnr_slug"):
        if grp.empty:
            continue
        player_row = grp.iloc[0]
        current_pos = player_row["position_group"]

        # Score dans le poste actuel (contexte : tous les joueurs du même poste)
        pos_pool = df[df["position_group"] == current_pos]
        w_current = NAIM_POS_WEIGHTS.get(current_pos, {})
        if not w_current:
            continue

        # Score du joueur dans son poste natif
        scores_current = _compute_score_for_pos(pos_pool.copy(), w_current)
        player_idx_in_pool = pos_pool.index.get_loc(player_row.name) if player_row.name in pos_pool.index else None
        if player_idx_in_pool is None:
            continue
        score_current = float(scores_current[player_idx_in_pool])

        best_alt_pos   = None
        best_alt_score = score_current

        for alt_pos, w_alt in NAIM_POS_WEIGHTS.items():
            if alt_pos == current_pos:
                continue
            # Évaluer dans le contexte du poste alternatif (pool alt_pos)
            alt_pool = df[df["position_group"] == alt_pos].copy()
            # Ajouter le joueur courant au pool alternatif pour normalisation correcte
            player_df = grp.copy()
            combined  = pd.concat([alt_pool, player_df]).reset_index(drop=True)

            scores_alt = _compute_score_for_pos(combined, w_alt)
            # Le joueur est ajouté à la fin
            player_score_alt = float(scores_alt[-len(player_df):].mean())

            if player_score_alt > best_alt_score:
                best_alt_score = player_score_alt
                best_alt_pos   = alt_pos

        delta = best_alt_score - score_current
        if best_alt_pos and delta >= delta_threshold:
            rows.append({
                "lnr_slug":          str(slug),
                "name":              player_row.get("name", ""),
                "team":              player_row.get("team", ""),
                "current_pos":       current_pos,
                "suggested_pos":     best_alt_pos,
                "score_current":     round(score_current, 1),
                "score_suggested":   round(best_alt_score, 1),
                "delta":             round(delta, 1),
                "already_overridden": str(slug) in overridden_slugs,
            })

    if not rows:
        return pd.DataFrame()

    result = (
        pd.DataFrame(rows)
          .sort_values("delta", ascending=False)
          .head(max_suggestions)
          .reset_index(drop=True)
    )
    return result


def format_audit_table(df_suggestions: pd.DataFrame) -> pd.DataFrame:
    """Met en forme le DataFrame pour l'affichage Streamlit."""
    if df_suggestions.empty:
        return df_suggestions
    df = df_suggestions.copy()
    df["delta"] = df["delta"].apply(lambda x: f"+{x:.1f}")
    df["already_overridden"] = df["already_overridden"].apply(
        lambda x: "✅ déjà corrigé" if x else "⚠️ à vérifier"
    )
    return df.rename(columns={
        "lnr_slug":          "Slug LNR",
        "name":              "Joueur",
        "team":              "Équipe",
        "current_pos":       "Poste actuel",
        "suggested_pos":     "Poste suggéré",
        "score_current":     "Score actuel",
        "score_suggested":   "Score suggéré",
        "delta":             "Gain",
        "already_overridden": "Statut",
    })
