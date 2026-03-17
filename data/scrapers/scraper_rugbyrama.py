"""
Scraper Rugbyrama — source secondaire.

Cible : https://www.rugbyrama.fr/rugby/top-14/
         https://www.rugbyrama.fr/rugby/top-14/statistiques/

Donnees recuperees :
- Profil joueur : age, nationalite, taille, poids (non disponibles sur LNR)
- Stats complementaires si LNR est incomplet
- Historique saison pour stabilite

Usage :
    python scraper_rugbyrama.py --season 2023-2024 --players ../raw/lnr_raw.json
    python scraper_rugbyrama.py --season 2023-2024 --output ../raw/rugbyrama_raw.json
"""

import argparse
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.rugbyrama.fr"
STATS_URL = "https://www.rugbyrama.fr/rugby/top-14/statistiques"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://www.rugbyrama.fr/",
}

REQUEST_DELAY = 2.5  # secondes — Rugbyrama est plus strict

# Mapping colonnes Rugbyrama -> schema interne
RUGBYRAMA_COLUMN_MAP = {
    "Joueur": "name",
    "Club": "team",
    "Poste": "position_raw",
    "Nationalite": "nationality",
    "Age": "age",
    "Taille": "height_cm",
    "Poids": "weight_kg",
    "Matchs": "matches_played",
    "Tps de jeu (min)": "minutes_total",
    "Plaquages": "tackles_total",
    "% Reussite plaquages": "tackle_success_pct",
    "Courses": "carries_total",
    "Metres": "meters_total",
    "Franchissements": "line_breaks_total",
    "Offloads": "offloads_total",
    "Passes": "passes_total",
    "Metres au pied": "kick_meters_total",
    "Points": "points_scored_total",
    "En-avant": "errors_total",
    "Penalites": "penalties_total",
    "Turnovers perdus": "turnovers_lost_total",
    "Turnovers gagnes": "turnovers_won_total",
    "Arrives au ruck": "ruck_arrivals_total",
    "Touches gagnees": "lineout_wins_total",
    "% Melee": "scrum_success_pct",
}

# Stats categories Rugbyrama
STAT_TABS = ["general", "attaque", "defense", "discipline", "coups-de-pied"]

# Mapping positions Rugbyrama (Mode Groupes LNR)
POSITION_MAP = {
    "Pilier gauche": "FRONT_ROW",
    "Pilier droit": "FRONT_ROW",
    "Pilier": "FRONT_ROW",
    "Talonneur": "FRONT_ROW",
    "2eme ligne": "LOCK",
    "Flanker": "BACK_ROW",
    "3eme ligne aile": "BACK_ROW",
    "Numero 8": "BACK_ROW",
    "3eme ligne centre": "BACK_ROW",
    "Demi de melee": "SCRUM_HALF",
    "Demi d'ouverture": "FLY_HALF",
    "Ailier": "WINGER",
    "Centre": "CENTRE",
    "Arriere": "FULLBACK",
}

# Drapeaux nationalites
NATIONALITY_FLAGS = {
    "France": "FR", "Afrique du Sud": "ZA", "Nouvelle-Zelande": "NZ",
    "Australie": "AU", "Angleterre": "ENG", "Irlande": "IRL",
    "Ecosse": "SCO", "Pays de Galles": "WAL", "Argentine": "ARG",
    "Fidji": "FIJ", "Samoa": "SAM", "Tonga": "TON",
    "Italie": "ITA", "Uruguay": "URU", "Georgie": "GEO",
    "Namibie": "NAM", "Roumanie": "ROU", "Canada": "CAN",
    "USA": "USA", "Japon": "JPN",
}


# ---------------------------------------------------------------------------
# Session HTTP
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def safe_get(session: requests.Session, url: str, params: dict = None,
             retries: int = 3) -> requests.Response | None:
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 429:
                wait = 45 * (attempt + 1)
                print(f"  [429] Rate limited. Attente {wait}s...")
                time.sleep(wait)
            elif resp.status_code in (403, 406):
                print(f"  [{resp.status_code}] Acces refuse : {url}")
                return None
            else:
                print(f"  [{resp.status_code}] Erreur temporaire : {url}")
                time.sleep(REQUEST_DELAY * 3)
        except requests.RequestException as e:
            print(f"  [ERREUR] {e} — tentative {attempt + 1}/{retries}")
            time.sleep(REQUEST_DELAY * 2)
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_stat_table(html: str, tab: str) -> list[dict]:
    """Parse un tableau de stats Rugbyrama."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    # Rugbyrama peut utiliser des tableaux ou des grids
    table = soup.find("table")
    if not table:
        print(f"  [WARN] Pas de tableau trouve pour onglet '{tab}'")
        return []

    headers = []
    thead = table.find("thead")
    if thead:
        headers = [
            RUGBYRAMA_COLUMN_MAP.get(th.get_text(strip=True), th.get_text(strip=True))
            for th in thead.find_all("th")
        ]

    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells or len(cells) < 3:
            continue
        row = {headers[i] if i < len(headers) else f"col_{i}": cell.get_text(strip=True)
               for i, cell in enumerate(cells)}
        row["_tab"] = tab
        rows.append(row)

    return rows


def enrich_player_profile(session: requests.Session, player_url: str) -> dict:
    """
    Recupere la page profil d'un joueur pour age, nationalite, taille, poids.
    Retourne un dict avec les donnees supplementaires.
    """
    resp = safe_get(session, player_url)
    if not resp:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    profile = {}

    # Cherche les metadata du profil (structure variable selon version Rugbyrama)
    info_blocks = soup.find_all(class_=re.compile(r"profile|bio|info|player-detail", re.I))
    for block in info_blocks:
        text = block.get_text(separator="\n")
        # Age
        age_match = re.search(r"Age\s*:?\s*(\d+)", text, re.I)
        if age_match:
            profile["age"] = int(age_match.group(1))
        # Nationalite
        nat_match = re.search(r"Nationalit[e\xe9]\s*:?\s*([A-Za-z\s]+)", text, re.I)
        if nat_match:
            profile["nationality"] = nat_match.group(1).strip()
        # Taille
        taille_match = re.search(r"Taille\s*:?\s*(\d+)\s*cm", text, re.I)
        if taille_match:
            profile["height_cm"] = int(taille_match.group(1))
        # Poids
        poids_match = re.search(r"Poids\s*:?\s*(\d+)\s*kg", text, re.I)
        if poids_match:
            profile["weight_kg"] = int(poids_match.group(1))

    return profile


# ---------------------------------------------------------------------------
# Scraping principal
# ---------------------------------------------------------------------------

def scrape_player_stats(session: requests.Session, season: str) -> list[dict]:
    """
    Scrape les stats Rugbyrama pour une saison.
    """
    print(f"\n[Rugbyrama] Scraping stats joueurs saison {season}...")
    all_rows = []

    for tab in STAT_TABS:
        url = f"{STATS_URL}/{tab}"
        print(f"  -> Onglet: {tab}")

        resp = safe_get(session, url, params={"saison": season})
        if not resp:
            print(f"  [WARN] Echec pour onglet {tab}")
            continue

        rows = parse_stat_table(resp.text, tab)
        print(f"     {len(rows)} lignes parsees")
        all_rows.extend(rows)
        time.sleep(REQUEST_DELAY)

    # Deduplication par joueur
    players: dict[tuple, dict] = {}
    for row in all_rows:
        key = (row.get("name", "").strip(), row.get("team", "").strip())
        if not key[0]:
            continue
        if key not in players:
            players[key] = {"name": key[0], "team": key[1], "_source": "rugbyrama"}
        for k, v in row.items():
            if k not in ("_tab",) and k not in players[key]:
                players[key][k] = v

    result = list(players.values())
    print(f"\n  -> {len(result)} joueurs uniques")
    return result


def enrich_with_profiles(session: requests.Session, players: list[dict],
                          player_index: dict) -> list[dict]:
    """
    Pour chaque joueur LNR sans nationalite, cherche son profil Rugbyrama.
    player_index : dict name -> URL profil (pre-construit par search)
    """
    enriched = 0
    for player in players:
        if player.get("nationality"):
            continue
        name = player.get("name", "")
        url = player_index.get(name)
        if not url:
            continue
        extras = enrich_player_profile(session, url)
        if extras:
            player.update({k: v for k, v in extras.items() if not player.get(k)})
            enriched += 1
        time.sleep(REQUEST_DELAY)

    print(f"  -> {enriched} joueurs enrichis avec profils Rugbyrama")
    return players


def search_player_url(session: requests.Session, name: str) -> str | None:
    """Recherche l'URL profil d'un joueur sur Rugbyrama."""
    search_url = f"{BASE_URL}/recherche"
    resp = safe_get(session, search_url, params={"q": name})
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    # Cherche un lien vers le profil joueur
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/joueur/" in href or "/player/" in href:
            if name.split()[-1].lower() in a.get_text().lower():
                return BASE_URL + href if href.startswith("/") else href
    return None


# ---------------------------------------------------------------------------
# Fusion avec donnees LNR
# ---------------------------------------------------------------------------

def merge_with_lnr(lnr_players: list[dict], rugbyrama_players: list[dict]) -> list[dict]:
    """
    Enrichit les joueurs LNR avec les donnees Rugbyrama (nationalite, age, physique).
    Strategie : LNR est authoritative pour les stats, Rugbyrama complete le profil.
    """
    # Index Rugbyrama par nom normalise
    rr_index = {}
    for p in rugbyrama_players:
        key = _normalize_name(p.get("name", ""))
        rr_index[key] = p

    merged = 0
    for player in lnr_players:
        key = _normalize_name(player.get("name", ""))
        rr_data = rr_index.get(key)
        if not rr_data:
            # Essai avec nom partiel (nom de famille)
            last_name = key.split("_")[-1] if "_" in key else key
            for rr_key, rr_p in rr_index.items():
                if last_name in rr_key and last_name:
                    rr_data = rr_p
                    break

        if rr_data:
            # Completer les champs manquants uniquement
            for field in ["nationality", "age", "height_cm", "weight_kg"]:
                if not player.get(field) and rr_data.get(field):
                    player[field] = rr_data[field]
            # Completer les stats manquantes
            for field in ["tackles_per80", "carries_per80", "passes_per80"]:
                if player.get(field) is None and rr_data.get(field) is not None:
                    player[field] = rr_data[field]
                    player["_source"] = "lnr+rugbyrama"
            merged += 1

    print(f"[Merge] {merged}/{len(lnr_players)} joueurs enrichis depuis Rugbyrama")
    return lnr_players


def _normalize_name(name: str) -> str:
    """Normalise un nom pour comparaison : minuscules, sans accents, underscore."""
    name = name.lower().strip()
    replacements = {
        "e\xe9": "e", "\xe8": "e", "\xea": "e",
        "\xe0": "a", "\xe2": "a",
        "\xf4": "o", "\xf6": "o",
        "\xfb": "u", "\xfc": "u",
        "\xe7": "c", "\xee": "i",
    }
    for old, new in replacements.items():
        for char in old:
            name = name.replace(char, new)
    name = re.sub(r"[^a-z0-9]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper Rugbyrama (complement LNR)")
    parser.add_argument("--season", default="2023-2024")
    parser.add_argument("--players", default=None,
                        help="Fichier LNR JSON a enrichir (optionnel)")
    parser.add_argument("--output", default="../raw/rugbyrama_raw.json")
    parser.add_argument("--merged-output", default="../raw/players_merged.json",
                        help="Sortie fusionnee LNR + Rugbyrama")
    args = parser.parse_args()

    session = make_session()
    output_path = Path(__file__).parent / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Scraping Rugbyrama
    rr_players = scrape_player_stats(session, args.season)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rr_players, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] {len(rr_players)} joueurs Rugbyrama -> {output_path}")

    # Fusion avec LNR si fourni
    if args.players:
        lnr_path = Path(__file__).parent / args.players
        if lnr_path.exists():
            with open(lnr_path, encoding="utf-8") as f:
                lnr_players = json.load(f)
            merged = merge_with_lnr(lnr_players, rr_players)
            merged_path = Path(__file__).parent / args.merged_output
            with open(merged_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            print(f"[OK] {len(merged)} joueurs fusionnes -> {merged_path}")


if __name__ == "__main__":
    main()
