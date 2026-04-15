"""
Fonctions partagées entre toutes les pages Streamlit.
"""

import json
import os
import sys
import pandas as pd
import streamlit as st

# S'assurer que le répertoire racine est dans le PATH
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.ratings import calculate_ratings, get_team_strength, apply_historical_prior


DATA_PATH = os.path.join(ROOT, "data", "players.csv")
# players_scored.csv = players.csv + ratings pré-calculés par le pipeline (step_score)
DATA_SCORED_PATH = os.path.join(ROOT, "data", "players_scored.csv")

# Postes groupe LNR-only (jamais de postes fins sans Statbunker)
POSITIONS_LNR_GROUPS = ["FRONT_ROW", "LOCK", "BACK_ROW", "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK"]
# Postes fins (uniquement disponibles avec Statbunker)
POSITIONS_FINE = ["PROP", "HOOKER", "LOCK", "FLANKER", "NUMBER_8", "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK"]


def get_available_positions(df: pd.DataFrame) -> list[str]:
    """
    Retourne la liste des groupes de poste disponibles dans df.
    Filtre HOOKER et NUMBER_8 si la source est LNR-only (pas de Statbunker).
    Source unique de vérité pour tous les dropdowns UI.
    """
    has_statbunker = (
        "position_source" in df.columns and (df["position_source"] == "sb").any()
    )
    fine_only = {"HOOKER", "NUMBER_8", "PROP", "FLANKER"}
    available = sorted(df["position_group"].dropna().unique().tolist())
    if not has_statbunker:
        available = [p for p in available if p not in fine_only]
    return available


def load_source_mode() -> str:
    """
    Lit source_mode depuis pipeline_run_metadata.json.
    Retourne 'LNR_ONLY' ou 'LNR_SB_MIXED'.
    """
    meta_path = os.path.join(ROOT, "data", "pipeline_run_metadata.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get("source_mode", "LNR_ONLY")
    except Exception:
        return "LNR_ONLY"


SEASONS_DIR = os.path.join(ROOT, "data", "seasons")
POST_COVID_SEASONS = ["2020-2021","2021-2022","2022-2023","2023-2024","2024-2025","2025-2026"]


def get_available_seasons() -> list[str]:
    """Retourne les saisons disponibles dans data/seasons/ (ordre chronologique)."""
    available = []
    for s in POST_COVID_SEASONS:
        path = os.path.join(SEASONS_DIR, s, "players_scored.csv")
        if os.path.exists(path):
            available.append(s)
    # Toujours inclure la saison courante si players_scored.csv existe à la racine
    if not available and os.path.exists(DATA_SCORED_PATH):
        available.append("2025-2026")
    return available


ALL_SEASONS_PATH = os.path.join(ROOT, "data", "players_all_seasons.csv")


def _enrich_with_prior(df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Ajoute rating_value + display_rating via prior historique."""
    if "rating_value" not in df.columns:
        df = apply_historical_prior(df, ALL_SEASONS_PATH, current_season=season)
    # Fallback : display_rating = rating si la colonne est absente (CSV ancien format)
    if "display_rating" not in df.columns:
        df["display_rating"] = df["rating"]
    return df


@st.cache_data(show_spinner="Chargement des données...", ttl=3600)
def load_data(season: str = "2025-2026") -> pd.DataFrame:
    """
    Charge les données joueurs + ratings pour une saison donnée.
    Cherche d'abord dans data/seasons/{season}/, sinon fallback sur data/ (saison courante).
    Injecte rating_value (blend saison + prior historique).
    """
    # Priorité : seasons/{season}/players_scored.csv
    season_scored = os.path.join(SEASONS_DIR, season, "players_scored.csv")
    if os.path.exists(season_scored):
        df = pd.read_csv(season_scored)
        if "rating" in df.columns:
            print(f"[LOAD] seasons/{season}/players_scored.csv ({len(df)} joueurs)")
            return _enrich_with_prior(df, season)

    # Fallback : saison courante dans data/
    if season == "2025-2026":
        if os.path.exists(DATA_SCORED_PATH):
            scored_fresh = True
            if os.path.exists(DATA_PATH):
                scored_fresh = os.path.getmtime(DATA_SCORED_PATH) >= os.path.getmtime(DATA_PATH)
            if scored_fresh:
                df = pd.read_csv(DATA_SCORED_PATH)
                if "rating" in df.columns and "axis_att" in df.columns:
                    print(f"[LOAD] data/players_scored.csv ({len(df)} joueurs)")
                    return _enrich_with_prior(df, season)

        if not os.path.exists(DATA_PATH):
            st.error("Fichier data/players.csv introuvable.\n\nLance d'abord le pipeline.")
            st.stop()
        df = pd.read_csv(DATA_PATH)
        df = calculate_ratings(df)
        print(f"[LOAD] data/players.csv (recalcul ratings) ({len(df)} joueurs)")
        return _enrich_with_prior(df, season)

    st.error(f"Données manquantes pour la saison {season}.\nLancer : `python data/scrapers/scrape_all_seasons.py --seasons {season}`")
    st.stop()


@st.cache_data(show_spinner=False)
def load_team_strength(season: str = "2025-2026") -> pd.DataFrame:
    df = load_data(season)
    return get_team_strength(df)


def season_selector(key_suffix: str = "") -> str:
    """
    Affiche un sélecteur de saison dans la sidebar et retourne la saison choisie.
    Lit st.session_state['selected_season'] si défini par Home.py (navigation globale).
    """
    available = get_available_seasons()
    default = st.session_state.get("selected_season", available[-1] if available else "2025-2026")
    if not available or len(available) == 1:
        return available[0] if available else "2025-2026"
    season = st.sidebar.selectbox(
        "Saison",
        available[::-1],
        index=available[::-1].index(default) if default in available[::-1] else 0,
        key=f"season_sidebar{key_suffix}",
    )
    st.session_state["selected_season"] = season
    return season


def rating_mode_selector(key_suffix: str = "") -> str:
    """
    Affiche un toggle 'Note Saison / Note Valeur' dans la sidebar.
    Retourne 'rating' ou 'rating_value'.
    Lit/écrit st.session_state['rating_mode'].
    """
    current = st.session_state.get("rating_mode", "saison")
    mode = st.sidebar.radio(
        "Mode de notation",
        ["saison", "valeur"],
        index=0 if current == "saison" else 1,
        format_func=lambda x: "Note Saison" if x == "saison" else "Note Valeur (historique)",
        key=f"rating_mode{key_suffix}",
        help=(
            "**Note Saison** : performance en Top14 cette saison uniquement.\n\n"
            "**Note Valeur** : blend avec l'historique des 2 dernières saisons — "
            "stabilise les internationaux peu utilisés en club (ex. Dupont)."
        ),
    )
    st.session_state["rating_mode"] = mode
    return "rating_value" if mode == "valeur" else "display_rating"


def get_rating_col() -> str:
    """Retourne la colonne de rating active selon le mode sélectionné."""
    return "rating_value" if st.session_state.get("rating_mode") == "valeur" else "display_rating"


def page_config(title: str):
    st.set_page_config(
        page_title=f"Rugby Rating Engine — {title}",
        page_icon="🏉",
        layout="wide",
    )


TIER_COLORS = {
    "LEGENDAIRE": "#FFD700",
    "OR":         "#C8A840",
    "ARGENT":     "#3A7A28",
    "BRONZE":     "#8C4020",
    "STANDARD":   "#585858",
}


def rating_to_tier(r: float) -> str:
    if r >= 90: return "LEGENDAIRE"
    if r >= 84: return "OR"
    if r >= 77: return "ARGENT"
    if r >= 70: return "BRONZE"
    return "STANDARD"


def rating_badge(r: float) -> str:
    """Retourne un badge HTML coloré pour le rating."""
    tier = rating_to_tier(r)
    color = TIER_COLORS[tier]
    return f'<span style="background:{color};color:#000;padding:2px 8px;border-radius:4px;font-weight:bold">{int(r)}</span>'


AXIS_LABELS = {
    "axis_att":  "Course",
    "axis_def":  "Physique",
    "axis_disc": "Rigueur",
    "axis_ctrl": "Distribution",
    "axis_kick": "Kicking",
    "axis_pow":  "Danger",
}

# Description détaillée de chaque axe v4 — architecture Naim
AXIS_DESCRIPTIONS = {
    "axis_att": {
        "label": "Course (Franchissements)",
        "emoji": "🏃",
        "metrics": ["Franchissements /80 (line breaks)"],
        "note": "Normalisé par poste [p5–p95]. Mesure la capacité à gagner du terrain balle en main.",
    },
    "axis_def": {
        "label": "Physique (Défense)",
        "emoji": "🛡️",
        "metrics": ["Plaquages réussis /80"],
        "note": "Normalisé par poste [p5–p95]. Forwards naturellement favorisés (volume de plaquages).",
    },
    "axis_disc": {
        "label": "Rigueur (Discipline)",
        "emoji": "🟡",
        "metrics": ["Cartons per80 inversé"],
        "note": "100 = parfaitement discipliné. Jaune 0.6pt, Orange 1.2pt, Rouge 2.0pt / 80min.",
    },
    "axis_ctrl": {
        "label": "Distribution (Jeu de bras)",
        "emoji": "⚡",
        "metrics": ["Offloads /80"],
        "note": "Proxy distribution. Normalisé par poste. Backs et 3e ligne favorisés.",
    },
    "axis_kick": {
        "label": "Kicking (Impact points)",
        "emoji": "👟",
        "metrics": ["Points marqués /80"],
        "note": "Poids fort pour ouvreurs (25%) et arrières (16%). Poids nul pour avants.",
    },
    "axis_pow": {
        "label": "Danger (Menace offensive)",
        "emoji": "💪",
        "metrics": ["Essais /80 (×0.6)", "Grattages /80 (×0.4)"],
        "note": "Combine capacité à marquer et à créer des occasions. Poids Naim par poste.",
    },
}

# Couleurs par équipe (pour avatars)
TEAM_COLORS = {
    "Stade Toulousain":  "#8B0000",
    "Bordeaux-Begles":   "#003366",
    "Stade Rochelais":   "#B8860B",
    "Racing 92":         "#4169E1",
    "ASM Clermont":      "#FFD700",
    "Stade Francais":    "#CC0066",
    "RC Toulon":         "#CC0000",
    "LOU Rugby":         "#B22222",
    "Castres Olympique": "#2F6B3D",
    "Montpellier HRC":   "#003087",
    "USAP Perpignan":    "#C8102E",
    "Aviron Bayonnais":  "#006400",
    "CA Brive":          "#8B4513",
    "Section Paloise":   "#228B22",
}


LNR_PHOTO_HASH = "b5e9990d9a31ede8327da9bafe6aeb896ea144f3"
PHOTOS_CACHE_DIR = os.path.join(ROOT, "data", "photos")


def get_photo_url(player: dict) -> str | None:
    """Retourne l'URL CDN LNR de la photo du joueur.
    Priorité : photo_url scraped (hash exact) > construit depuis lnr_id/lnr_slug.
    """
    stored = player.get("photo_url")
    if stored and str(stored) not in ("nan", "None", ""):
        return str(stored)
    lnr_id = player.get("lnr_id")
    lnr_slug = player.get("lnr_slug")
    if not lnr_id or not lnr_slug or str(lnr_id) == "nan":
        return None
    return (
        f"https://cdn.lnr.fr/joueur/{int(float(lnr_id))}-{lnr_slug}"
        f"/photo/photoFull.{LNR_PHOTO_HASH}"
    )


@st.cache_data(show_spinner=False, ttl=86400)
def fetch_player_photo_bytes(photo_url: str) -> bytes | None:
    """
    Télécharge la photo LNR et la met en cache (1 jour).
    Retourne None si indisponible.
    """
    try:
        import requests as _req
        r = _req.get(photo_url, timeout=5)
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            return r.content
    except Exception:
        pass
    return None


def hex_rgba(h: str, a: float = 0.2) -> str:
    """Convertit #RRGGBB en rgba(r,g,b,a) valide pour Plotly."""
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"rgba({r},{g},{b},{a})"

AXIS_COLORS = {
    "axis_att":  "#EF4444",
    "axis_def":  "#3B82F6",
    "axis_disc": "#10B981",
    "axis_ctrl": "#F59E0B",
    "axis_kick": "#8B5CF6",
    "axis_pow":  "#EC4899",
}

NATIONALITY_FLAG: dict[str, str] = {
    "France":                      "🇫🇷",
    "Angleterre":                  "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Irlande":                     "🇮🇪",
    "Ecosse":                      "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Pays de Galles":              "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Italie":                      "🇮🇹",
    "Argentine":                   "🇦🇷",
    "Afrique du Sud":              "🇿🇦",
    "Australie":                   "🇦🇺",
    "Nouvelle Zélande":            "🇳🇿",
    "Nouvelle Zéeland":            "🇳🇿",
    "Nouvelle Z\u00e9lande":       "🇳🇿",
    "Fidji":                       "🇫🇯",
    "Samoa":                       "🇼🇸",
    "Samoa occidental":            "🇼🇸",
    "Samoa américain":             "🇦🇸",
    "Tonga":                       "🇹🇴",
    "Japon":                       "🇯🇵",
    "Géorgie":                     "🇬🇪",
    "G\u00e9orgie":                "🇬🇪",
    "Roumanie":                    "🇷🇴",
    "Uruguay":                     "🇺🇾",
    "Namibie":                     "🇳🇦",
    "Chili":                       "🇨🇱",
    "Portugal":                    "🇵🇹",
    "Espagne":                     "🇪🇸",
    "Allemagne":                   "🇩🇪",
    "Belgique":                    "🇧🇪",
    "Canada":                      "🇨🇦",
    "Etats-Unis":                  "🇺🇸",
    "États-Unis":                  "🇺🇸",
    "Russie":                      "🇷🇺",
    "Moldavie":                    "🇲🇩",
    "Autriche":                    "🇦🇹",
    "Grande-Bretagne":             "🇬🇧",
    "Cameroun":                    "🇨🇲",
    "Zimbabwe":                    "🇿🇼",
    "République Démocratique du Congo": "🇨🇩",
    "R\u00e9publique D\u00e9mocratique du Congo": "🇨🇩",
}


def nat_flag(nationality: str) -> str:
    """Retourne le drapeau emoji pour une nationalité, '' si inconnu."""
    if not nationality or str(nationality) in ("nan", "None", ""):
        return ""
    return NATIONALITY_FLAG.get(str(nationality).strip(), "🏳️")
