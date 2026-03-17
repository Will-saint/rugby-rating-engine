"""
Match Predictor — score prédictif basé sur les forces d'équipe.

Modèle simple mais calibré :
  - Différence de Team Strength Score
  - Avantage domicile (+3 pts d'écart perçus)
  - Forme récente (±5 pts)
  - Fonction logistique → probabilité de victoire
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


HOME_ADVANTAGE = 3.5   # Points de rating bonus pour l'équipe à domicile
SCALE_FACTOR = 0.065   # Calibration de la fonction logistique


@dataclass
class MatchPrediction:
    home_team: str
    away_team: str
    home_win_pct: float
    away_win_pct: float
    draw_pct: float
    predicted_margin: float       # Écart de points prédit (positif = domicile gagne)
    expected_home_score: float
    expected_away_score: float
    confidence: str               # "Haute", "Moyenne", "Faible"
    risk_flag: bool               # Match à risque (serré)


def logistic(x: float) -> float:
    """Fonction logistique bornée entre 0 et 1."""
    return 1.0 / (1.0 + np.exp(-x))


def predict_match(
    home_rating: float,
    away_rating: float,
    home_att: float,
    home_def: float,
    away_att: float,
    away_def: float,
    home_form: float = 0.0,   # -1 (mauvaise forme) à +1 (excellente forme)
    away_form: float = 0.0,
    neutral_venue: bool = False,
) -> MatchPrediction:
    """
    Prédit le résultat d'un match.

    home_rating / away_rating : Team Strength Score (0-100)
    home_att / def / away_att / def : indices d'attaque/défense (0-100)
    home_form / away_form : facteur de forme récente (-1 à +1)
    """
    # Avantage terrain
    venue_bonus = 0.0 if neutral_venue else HOME_ADVANTAGE

    # Forme récente (±5 pts de rating effectif)
    home_effective = home_rating + venue_bonus + home_form * 5
    away_effective = away_rating + away_form * 5

    # Différentiel
    delta = home_effective - away_effective

    # Probabilité de victoire domicile (logistique)
    home_win_prob = logistic(SCALE_FACTOR * delta)

    # Probabilité de nul (faible au rugby, ~3-5%)
    draw_prob = max(0.02, 0.06 - abs(delta) * 0.003)
    draw_prob = min(draw_prob, 0.06)

    # Redistribution
    net = home_win_prob - draw_prob / 2
    away_win_prob = 1.0 - net - draw_prob
    away_win_prob = max(0.01, away_win_prob)

    # Re-normaliser
    total = net + away_win_prob + draw_prob
    home_win_prob = net / total
    away_win_prob = away_win_prob / total
    draw_prob = draw_prob / total

    # Écart prédit (en points de match)
    # Corrélation approximative : 1 pt de rating ~ 0.6 pt de score
    predicted_margin = delta * 0.6

    # Scores estimés (base ~22 pts par équipe au Top 14)
    base_score = 22.0
    home_score = base_score + predicted_margin / 2
    away_score = base_score - predicted_margin / 2

    # Ajustement ATT/DEF cross
    home_score += (home_att - away_def) * 0.04
    away_score += (away_att - home_def) * 0.04

    home_score = max(0, round(home_score, 1))
    away_score = max(0, round(away_score, 1))

    # Confiance
    margin_abs = abs(delta)
    if margin_abs >= 12:
        confidence = "Haute"
    elif margin_abs >= 6:
        confidence = "Moyenne"
    else:
        confidence = "Faible"

    risk_flag = margin_abs < 5

    return MatchPrediction(
        home_team="Domicile",
        away_team="Extérieur",
        home_win_pct=round(home_win_prob * 100, 1),
        away_win_pct=round(away_win_prob * 100, 1),
        draw_pct=round(draw_prob * 100, 1),
        predicted_margin=round(predicted_margin, 1),
        expected_home_score=home_score,
        expected_away_score=away_score,
        confidence=confidence,
        risk_flag=risk_flag,
    )
