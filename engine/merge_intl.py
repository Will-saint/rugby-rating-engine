"""
Merge Top14 ↔ International (Naim data).

Pour chaque joueur Top14, tente de trouver son équivalent dans
data/international_ratings.csv en matchant sur :
  1. Nom de famille normalisé (extrait du lnr_slug)
  2. Compatibilité de poste
  3. (optionnel) Initiale du prénom

Ajoute les colonnes intl aux joueurs matchés :
  rating_intl, team_intl, matches_intl, cluster_intl,
  axis_course_intl, axis_distrib_intl, axis_kicking_intl,
  axis_physique_intl, axis_rigueur_intl, axis_danger_intl, axis_melee_intl

Usage :
    from engine.merge_intl import enrich_with_intl
    df = enrich_with_intl(df_players)
"""
import os
import re
import unicodedata

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTL_PATH = os.path.join(ROOT, "data", "international_ratings.csv")

# Mapping poste LNR → positions Naim compatibles
POS_COMPAT: dict[str, set[str]] = {
    "PROP":       {"P"},
    "HOOKER":     {"H"},
    "FRONT_ROW":  {"P", "H"},
    "LOCK":       {"L"},
    "FLANKER":    {"FL"},
    "BACK_ROW":   {"N8", "FL"},
    "NUMBER_8":   {"N8"},
    "SCRUM_HALF": {"SH"},
    "FLY_HALF":   {"FH"},
    "WINGER":     {"W"},
    "CENTRE":     {"C"},
    "FULLBACK":   {"FB"},
}

INTL_AXIS_COLS = [
    "axis_course", "axis_distrib", "axis_kicking",
    "axis_physique", "axis_rigueur", "axis_danger", "axis_melee",
]


def _norm(s: str) -> str:
    """Normalise un nom : majuscules, sans accents, sans tirets."""
    s = str(s).upper().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[-_\s]+", " ", s).strip()
    return s


def _last_from_slug(slug: str) -> str:
    """Extrait le nom de famille depuis un lnr_slug.
    'barnabe-massa' → 'MASSA'
    'robert-simmons-1' → 'SIMMONS'
    'bryan-habana' → 'HABANA'
    """
    slug = re.sub(r"-\d+$", "", slug.lower())  # strip suffixe numérique
    parts = slug.split("-")
    if len(parts) == 1:
        return _norm(parts[0])
    return _norm(parts[-1])


def _first_initial_from_slug(slug: str) -> str:
    slug = re.sub(r"-\d+$", "", slug.lower())
    parts = slug.split("-")
    return parts[0][0].upper() if parts else ""


def _last_from_intl_name(name: str) -> str:
    """Extrait le nom de famille depuis le format Naim 'J CLIFFORD' ou 'L COWAN-DICKIE'."""
    name = _norm(name)
    parts = name.split()
    if len(parts) >= 2:
        return " ".join(parts[1:])  # tout après l'initiale
    return name


def _first_initial_from_intl(name: str) -> str:
    parts = _norm(name).split()
    return parts[0][0] if parts else ""


def build_intl_index(df_intl: pd.DataFrame) -> dict:
    """Construit un index {last_name → liste de rows} sur les données internationales."""
    idx: dict[str, list] = {}
    for _, row in df_intl.iterrows():
        last = _last_from_intl_name(row["name"])
        if last not in idx:
            idx[last] = []
        idx[last].append(row)
    return idx


def find_intl_match(
    lnr_slug: str,
    position_group: str,
    intl_index: dict,
) -> pd.Series | None:
    """Retourne la row internationale la plus probable pour un joueur Top14."""
    last = _last_from_slug(lnr_slug)
    initial = _first_initial_from_slug(lnr_slug)
    candidates = intl_index.get(last, [])

    if not candidates:
        return None

    pos_set = POS_COMPAT.get(position_group, set())

    # Filtre poste
    pos_matches = [r for r in candidates if r["position_naim"] in pos_set]
    if not pos_matches:
        # Fallback strict : ignorer le poste SEULEMENT si un seul candidat ET initiale confirmée
        if len(candidates) == 1 and candidates[0].get("position_naim") and initial:
            if _first_initial_from_intl(candidates[0]["name"]) == initial:
                pos_matches = candidates
        if not pos_matches:
            return None

    if len(pos_matches) == 1:
        return pos_matches[0]

    # Plusieurs candidats → valider par initiale
    init_matches = [r for r in pos_matches if _first_initial_from_intl(r["name"]) == initial]
    if init_matches:
        return init_matches[0]

    # Prendre le meilleur rating_intl (joueur le plus connu)
    return max(pos_matches, key=lambda r: r.get("rating_intl", 0))


def enrich_with_intl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute les colonnes intl aux joueurs Top14 matchés.
    Retourne df enrichi (colonnes intl NaN pour les non-matchés).
    """
    if not os.path.exists(INTL_PATH):
        return df

    df_intl = pd.read_csv(INTL_PATH)
    intl_index = build_intl_index(df_intl)

    # Préparer colonnes cibles
    for col in ["rating_intl", "team_intl", "matches_intl", "cluster_intl"] + [f"{c}_intl" for c in INTL_AXIS_COLS]:
        if col not in df.columns:
            df[col] = None

    matched = 0
    for idx, row in df.iterrows():
        slug = str(row.get("lnr_slug", ""))
        pos_group = str(row.get("position_group", ""))
        if not slug or slug == "nan":
            continue

        match = find_intl_match(slug, pos_group, intl_index)
        if match is None:
            continue

        df.at[idx, "rating_intl"] = round(float(match["rating_intl"]), 1)
        df.at[idx, "team_intl"] = match["team"]
        df.at[idx, "matches_intl"] = int(match.get("matches_intl", 0))
        df.at[idx, "cluster_intl"] = match.get("cluster", "")
        for col in INTL_AXIS_COLS:
            df.at[idx, f"{col}_intl"] = round(float(match[col]), 1)
        matched += 1

    print(f"[MERGE] {matched} joueurs Top14 matchés avec données internationales")
    return df
