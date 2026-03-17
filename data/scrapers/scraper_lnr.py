"""
Scraper LNR / Top14 — source primaire officielle.

URL de base : https://top14.lnr.fr

Données extraites SANS login (librement accessibles) :
  - Roster par équipe : player_id (LNR numeric), nom, position, stats de base
  - Profil joueur : taille, poids, âge, nationalité
  - Stats saison par joueur :
      matches_played, minutes_total, points_scored_total, tries_total,
      offloads_total, line_breaks_total, turnovers_won_total,
      tackles_success_total, yellow_cards, red_cards
  - Calendrier + résultats (scores, gagnant)
  - Événements match (essais, pénas, remplacements → minutes exactes)

Données NON disponibles sans login MyRugby :
  - carries, meters, passes, kick_meters, errors, penalties_conceded,
    total_tackles, ruck_arrivals, lineout_wins, scrum_pct
  → Compléter avec scraper_statbunker.py

Usage :
    python scraper_lnr.py --season 2023-2024 --output ../raw/lnr_raw.json
    python scraper_lnr.py --season 2023-2024 --with-matches
    python scraper_lnr.py --list-seasons
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

# Chemin racine pour les imports
sys.path.insert(0, str(Path(__file__).parent))
from http_client import RobustSession

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://top14.lnr.fr"


# ---------------------------------------------------------------------------
# URL Router — centralise toutes les routes LNR (évite les URLs en dur)
# ---------------------------------------------------------------------------

class LNR_ROUTES:
    """Constructeurs d'URL pour top14.lnr.fr — source unique de vérité."""

    @staticmethod
    def home() -> str:
        return BASE_URL

    @staticmethod
    def team_stats(slug: str, season: str) -> str:
        """Page statistiques joueurs d'un club pour une saison donnée.
        Note : la saison est dans le PATH (pas ?saison=) — format Vue.js router."""
        return f"{BASE_URL}/club/{slug}/statistiques/{season}"

    @staticmethod
    def team_calendar(slug: str) -> str:
        """Calendrier et résultats d'un club (saison courante seulement)."""
        return f"{BASE_URL}/club/{slug}/calendrier-resultats"

    @staticmethod
    def player_profile(lnr_id: int, slug: str) -> str:
        """Page profil d'un joueur (taille, poids, âge, nationalité)."""
        return f"{BASE_URL}/joueur/{lnr_id}-{slug}"


def test_routes() -> bool:
    """Test unitaire des constructeurs d'URL — aucun appel réseau requis."""
    cases = [
        (LNR_ROUTES.home(), "https://top14.lnr.fr"),
        (LNR_ROUTES.team_stats("toulouse", "2023-2024"),
         "https://top14.lnr.fr/club/toulouse/statistiques/2023-2024"),
        (LNR_ROUTES.team_stats("racing-92", "2025-2026"),
         "https://top14.lnr.fr/club/racing-92/statistiques/2025-2026"),
        (LNR_ROUTES.team_calendar("bordeaux-begles"),
         "https://top14.lnr.fr/club/bordeaux-begles/calendrier-resultats"),
        (LNR_ROUTES.player_profile(2461, "peato-mauvaka"),
         "https://top14.lnr.fr/joueur/2461-peato-mauvaka"),
    ]
    ok = True
    for got, expected in cases:
        if got != expected:
            print(f"  [FAIL] {got!r} != {expected!r}")
            ok = False
    if ok:
        print("  [OK] Tous les constructeurs d'URL sont corrects.")
    return ok


# IDs saisons LNR (extrait depuis le filtre seasons)
SEASON_IDS = {
    "2025-2026": 28,
    "2024-2025": 27,
    "2023-2024": 26,
    "2022-2023": 1,
    "2021-2022": 25,
    "2020-2021": 24,
}

# Mapping position (français LNR) → position_group interne
# Mode "Groupes LNR" : FRONT_ROW / LOCK / BACK_ROW pour les avants
# (LNR ne différencie pas Pilier vs Talonneur ni Flanker vs N°8 dans ses stats)
POSITION_FR_TO_GROUP = {
    # 1ère ligne = Piliers (1,3) + Talonneur (2) — LNR les regroupe
    "1ère ligne": "FRONT_ROW",
    "1ere ligne": "FRONT_ROW",
    "Pilier gauche": "FRONT_ROW",
    "Pilier droit": "FRONT_ROW",
    "Pilier": "FRONT_ROW",
    "Talonneur": "FRONT_ROW",
    # 2ème ligne = Locks
    "2ème ligne": "LOCK",
    "2eme ligne": "LOCK",
    "Deuxième ligne": "LOCK",
    # 3ème ligne = Flankers (6,7) + Numéro 8 — LNR les regroupe
    "3ème ligne": "BACK_ROW",
    "3eme ligne": "BACK_ROW",
    "3ème ligne aile": "BACK_ROW",
    "3eme ligne aile": "BACK_ROW",
    "Flanker": "BACK_ROW",
    "3ème ligne centre": "BACK_ROW",
    "3eme ligne centre": "BACK_ROW",
    "Numéro 8": "BACK_ROW",
    "Numero 8": "BACK_ROW",
    # Backs (inchangés — LNR est précis ici)
    "Demi de mêlée": "SCRUM_HALF",
    "Demi de melee": "SCRUM_HALF",
    "Demi d'ouverture": "FLY_HALF",
    "Ouvreur": "FLY_HALF",
    "Ailier": "WINGER",
    "Ailier Gauche": "WINGER",
    "Ailier Droit": "WINGER",
    "Centre Int.": "CENTRE",
    "Centre Ext.": "CENTRE",
    "Demi de M\u00e9l\u00e9e": "SCRUM_HALF",
    "Pilier Gauche": "FRONT_ROW",
    "Pilier Droit": "FRONT_ROW",
    "Flanker Aveugle": "BACK_ROW",
    "Flanker Ouvert": "BACK_ROW",
    "2\u00e8me Ligne": "LOCK",
    "Centre": "CENTRE",
    "Arrière": "FULLBACK",
    "Arriere": "FULLBACK",
}

# Noms canoniques équipes (LNR → interne)
TEAM_CANONICAL = {
    "Stade Toulousain": "Toulouse",
    "Racing 92": "Racing 92",
    "Stade Rochelais": "La Rochelle",
    "ASM Clermont": "Clermont",
    "Union Bordeaux-Bègles": "Bordeaux",
    "Union Bordeaux-Begles": "Bordeaux",
    "Castres Olympique": "Castres",
    "Montpellier Hérault Rugby": "Montpellier",
    "Montpellier Herault Rugby": "Montpellier",
    "LOU Rugby": "Lyon",
    "CA Brive": "Brive",
    "USA Perpignan": "Perpignan",
    "Section Paloise": "Pau",
    "RC Vannes": "Vannes",
    "RC Toulon": "Toulon",
    "Stade Français Paris": "Paris",
    "Stade Francais Paris": "Paris",
    "Aviron Bayonnais": "Bayonne",
    "US Montauban": "Montauban",
}

TEAM_CODES = {
    "Toulouse": "TLS", "Racing 92": "R92", "La Rochelle": "LRO",
    "Clermont": "CLR", "Bordeaux": "BOR", "Castres": "CAS",
    "Montpellier": "MHR", "Lyon": "LOU", "Brive": "BRI",
    "Perpignan": "PER", "Pau": "PAU", "Vannes": "VAN",
    "Toulon": "TLN", "Paris": "SFP", "Bayonne": "BAY", "Montauban": "MTB",
}

# Seuil de temps de jeu minimal (minutes totales saison) pour inclure un joueur
MIN_MINUTES_THRESHOLD = 40


# ---------------------------------------------------------------------------
# Parsing utilitaires
# ---------------------------------------------------------------------------

def _extract_vue_prop(soup: BeautifulSoup, tag_name: str, prop: str) -> list | dict | None:
    """Extrait la prop JSON d'un composant Vue.js dans le HTML."""
    el = soup.find(tag_name)
    if not el:
        return None
    raw = el.get(prop, "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_current_season(soup: BeautifulSoup) -> str | None:
    """Extrait le nom de la saison réellement servie par le site (depuis filters-fixtures)."""
    ff = soup.find("filters-fixtures")
    if not ff:
        return None
    raw = ff.get(":current-season", "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data.get("name")
    except (json.JSONDecodeError, AttributeError):
        return None


def _lnr_id_from_url(url: str) -> int | None:
    """Extrait l'ID numérique LNR depuis une URL joueur."""
    m = re.search(r"/joueur/(\d+)-", url)
    if m:
        return int(m.group(1))
    return None


def _slug_from_url(url: str) -> str:
    """Extrait le slug nom depuis une URL joueur : /joueur/2461-peato-mauvaka -> peato-mauvaka"""
    m = re.search(r"/joueur/\d+-(.+)$", url.rstrip("/"))
    return m.group(1) if m else ""


def _normalize_team(raw: str) -> str:
    clean = raw.strip()
    # Supprimer caractères UTF-8 variantes
    clean = clean.replace("\u00e8", "e").replace("\u00e9", "e").replace("\u00ea", "e")
    return TEAM_CANONICAL.get(clean, TEAM_CANONICAL.get(raw.strip(), raw.strip()))


def _team_code(team: str) -> str:
    return TEAM_CODES.get(team, team[:3].upper())


def _position_group(pos_fr: str) -> tuple[str, str]:
    """Mappe une position française vers (code_groupe, source).

    source values:
      lnr_explicit  — correspondance directe dans POSITION_FR_TO_GROUP
      lnr_keyword   — fallback par mots-clés
      unknown       — non reconnu
    """
    pos_clean = pos_fr.strip()
    # Essai direct
    if pos_clean in POSITION_FR_TO_GROUP:
        return POSITION_FR_TO_GROUP[pos_clean], "lnr_explicit"
    # Essai avec normalisation accents
    pos_norm = pos_clean.replace("\u00e8", "e").replace("\u00e9", "e").replace("\u00ea", "e")
    if pos_norm in POSITION_FR_TO_GROUP:
        return POSITION_FR_TO_GROUP[pos_norm], "lnr_explicit"
    # Fallback par mots clés
    pl = pos_clean.lower()
    if "piquier" in pl or "pilier" in pl or "talonneur" in pl or "hooker" in pl:
        return "FRONT_ROW", "lnr_keyword"
    if "2" in pl and "ligne" in pl:
        return "LOCK", "lnr_keyword"
    if "flanker" in pl or "aile" in pl or "8" in pl or ("3" in pl and "centre" in pl):
        return "BACK_ROW", "lnr_keyword"
    if "mêlée" in pl or "melee" in pl:
        return "SCRUM_HALF", "lnr_keyword"
    if "ouverture" in pl or "fly" in pl:
        return "FLY_HALF", "lnr_keyword"
    if "ailier" in pl or "winger" in pl:
        return "WINGER", "lnr_keyword"
    if "centre" in pl:
        return "CENTRE", "lnr_keyword"
    if "arrière" in pl or "arriere" in pl or "fullback" in pl:
        return "FULLBACK", "lnr_keyword"
    return "UNKNOWN", "unknown"


def _to_int(val, default=0) -> int:
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return default


def _to_float(val) -> float | None:
    if val is None or str(val).strip() in ("", "-"):
        return None
    try:
        return float(str(val).replace(",", ".").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Smoke test saison (recommandation 1)
# ---------------------------------------------------------------------------

def season_smoke_test(session: RobustSession, season: str, reference_slug: str = "toulouse") -> bool:
    """
    Vérifie que la saison demandée == saison réellement servie par LNR.
    À exécuter AVANT le scraping massif.
    Retourne True si OK, False si mismatch ou erreur.
    """
    url = LNR_ROUTES.team_stats(reference_slug, season)
    html = session.get(url, timeout=20)
    if not html:
        session.logger.error(f"[SMOKE TEST] Impossible d'acceder a {url}")
        return False

    soup = BeautifulSoup(html, "lxml")
    served = _extract_current_season(soup)
    if served is None:
        session.logger.warning("[SMOKE TEST] Impossible d'extraire la saison servie (filters-fixtures absent ?)")
        # On continue prudemment (la page peut quand même avoir les bonnes données)
        return True
    if served != season:
        session.logger.error(
            f"[SMOKE TEST] FAIL — demandé={season}, servi={served} — "
            f"le site ne renvoie pas la bonne saison !"
        )
        return False

    session.logger.info(f"[SMOKE TEST] OK — saison {season} confirmée par le site")
    return True


# ---------------------------------------------------------------------------
# Étape 1 : Récupérer tous les slugs d'équipes
# ---------------------------------------------------------------------------

def scrape_team_list(session: RobustSession) -> list[dict]:
    """
    Récupère la liste des 14 équipes du Top14 depuis le footer de n'importe quelle page LNR.
    Retourne : [{name, slug, lnr_id, url}]
    """
    html = session.get(LNR_ROUTES.home(), snapshot_name="lnr_home")
    if not html:
        raise RuntimeError("Impossible d'accéder à top14.lnr.fr")

    soup = BeautifulSoup(html, "lxml")
    comps = _extract_vue_prop(soup, "footer-clubs", ":competitions")

    teams = []
    if comps and isinstance(comps, list):
        for comp in comps:
            if "TOP 14" in comp.get("name", ""):
                for club in comp.get("clubs", []):
                    club_url = club.get("url", "")
                    slug = club_url.split("/club/")[-1].strip("/") if "/club/" in club_url else ""
                    # Récupérer l'ID depuis l'URL logo (ex: cdn.lnr.fr/club/toulouse/...)
                    teams.append({
                        "name": club.get("name", ""),
                        "name_canonical": _normalize_team(club.get("name", "")),
                        "slug": slug,
                        "url": club_url,
                    })

    session.logger.info(f"Équipes trouvées : {len(teams)}")
    return teams


# ---------------------------------------------------------------------------
# Étape 2 : Stats joueurs par équipe (players-ranking JSON)
# ---------------------------------------------------------------------------

def scrape_team_player_stats(
    session: RobustSession,
    team_slug: str,
    season: str,
    team_name_canonical: str,
) -> list[dict]:
    """
    Récupère le JSON players-ranking de la page statistiques d'une équipe.
    Retourne une liste de dicts bruts (un par joueur).
    """
    url = LNR_ROUTES.team_stats(team_slug, season)
    html = session.get(url, snapshot_name=f"stats_{team_slug}_{season}")
    if not html:
        session.logger.warning(f"Impossible de charger stats : {team_slug}")
        return []

    soup = BeautifulSoup(html, "lxml")

    # Vérification saison réellement servie (recommandation 1)
    served_season = _extract_current_season(soup)
    if served_season and served_season != season:
        session.logger.error(
            f"SEASON MISMATCH pour {team_slug} : "
            f"demandé={season}, servi={served_season} — données ignorées"
        )
        return []

    ranking = _extract_vue_prop(soup, "players-ranking", ":ranking")
    if not ranking:
        session.logger.warning(f"players-ranking vide : {team_slug} (hors Top14 cette saison ?)")
        return []

    players = []
    for entry in ranking:
        player_info = entry.get("player", {})
        player_url = player_info.get("url", "")
        lnr_id = _lnr_id_from_url(player_url)
        slug = _slug_from_url(player_url)

        if not lnr_id:
            continue

        name_raw = player_info.get("name", "").strip()
        # LNR format: "Paul GRAOU" → "Paul Graou" pour normalisation
        name_parts = name_raw.split()
        name_display = " ".join(
            p.capitalize() if p.isupper() else p for p in name_parts
        )

        pos_fr = entry.get("position", "")
        pos_group, pos_source = _position_group(pos_fr)

        matches = _to_int(entry.get("nbMatchs", 0))
        minutes_total = _to_float(entry.get("minutesPlayed"))
        minutes_avg = (minutes_total / matches) if matches > 0 and minutes_total else None

        photo_url = player_info.get("image", {}).get("original") or None

        players.append({
            # Identité
            "lnr_id": lnr_id,
            "player_id": f"lnr_{lnr_id}",
            "lnr_slug": slug,
            "lnr_url": player_url,
            "photo_url": photo_url,
            "name": name_display,
            "name_raw": name_raw,
            "team": team_name_canonical,
            "team_slug": team_slug,
            "team_code": _team_code(team_name_canonical),
            "position_raw": pos_fr,
            "position_group": pos_group,
            "position_source": pos_source,
            "season": season,
            # Stats disponibles LNR (sans login)
            "matches_played": matches,
            "minutes_total": minutes_total,
            "minutes_avg": round(minutes_avg, 1) if minutes_avg else None,
            "points_scored_total": _to_float(entry.get("nbPoints")),
            "tries_total": _to_float(entry.get("nbEssais")),
            "offloads_total": _to_float(entry.get("offload")),
            "line_breaks_total": _to_float(entry.get("lineBreak")),
            "turnovers_won_total": _to_float(entry.get("breakdownSteals")),
            "tackles_success_total": _to_float(entry.get("totalSuccessfulTackles")),
            "yellow_cards": _to_int(entry.get("nbCartonsJaunes", 0)),
            "orange_cards": _to_int(entry.get("nbCartonsOranges", 0)),
            "red_cards": _to_int(entry.get("nbCartonsRouges", 0)),
            # Profil physique (rempli à l'étape suivante)
            "nationality": None,
            "age": None,
            "height_cm": None,
            "weight_kg": None,
            "_source": "lnr",
            "_profile_loaded": False,
        })

    session.logger.info(f"  {team_name_canonical}: {len(players)} joueurs")
    return players


# ---------------------------------------------------------------------------
# Étape 3 : Profil physique par joueur (/joueur/{id}-{slug})
# ---------------------------------------------------------------------------

def scrape_player_profile(
    session: RobustSession,
    lnr_id: int,
    lnr_slug: str,
) -> dict:
    """
    Récupère taille, poids, âge, nationalité depuis la page profil LNR.
    Retourne un dict avec les champs disponibles.
    """
    url = LNR_ROUTES.player_profile(lnr_id, lnr_slug)
    html = session.get(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    profile = {}

    # Structure LNR :
    #   <div class="player-infos__row"> (row 2) contient
    #   des <span class="player-infos__attribute"> avec icon + texte :
    #   [taille "1m84", poids "112 kg", âge "29 ans", nationalité "France"]
    attr_spans = soup.find_all("span", class_="player-infos__attribute")
    for span in attr_spans:
        # Le texte est le contenu du span hors de la balise <i>
        for i_tag in span.find_all("i"):
            i_tag.decompose()
        item = span.get_text(strip=True)
        if not item:
            continue
        h = re.match(r"1m(\d{2})", item)
        if h:
            profile["height_cm"] = int("1" + h.group(1))
            continue
        w = re.match(r"(\d{2,3})\s*kg", item)
        if w:
            profile["weight_kg"] = int(w.group(1))
            continue
        a = re.match(r"(\d{2})\s*ans", item)
        if a:
            age = int(a.group(1))
            if 16 <= age <= 45:
                profile["age"] = age
            continue
        # Nationalité : dernière span, commence par majuscule, sans chiffres
        if (
            item
            and item[0].isupper()
            and not any(c.isdigit() for c in item)
            and len(item) > 2
            and len(item) < 35
        ):
            profile["nationality"] = item

    # Fallback regex si la structure CSS a changé
    if not profile:
        text = soup.get_text(separator="\n")
        h = re.search(r"1m(\d{2})", text)
        if h:
            profile["height_cm"] = int("1" + h.group(1))
        w = re.search(r"(\d{2,3})\s*kg", text)
        if w:
            profile["weight_kg"] = int(w.group(1))
        a = re.search(r"(\d{2})\s*ans", text)
        if a:
            age = int(a.group(1))
            if 16 <= age <= 45:
                profile["age"] = age

    return profile


# ---------------------------------------------------------------------------
# Étape 4 : Calendrier + résultats
# ---------------------------------------------------------------------------

def scrape_team_calendar(
    session: RobustSession,
    team_slug: str,
    season: str,
) -> list[dict]:
    """
    Récupère tous les matchs d'une équipe pour une saison.
    Retourne : [{season, round, date, team_home, team_away, score_home, score_away, match_url}]
    """
    url = LNR_ROUTES.team_calendar(team_slug)
    html = session.get(url, snapshot_name=f"calendar_{team_slug}_{season}")
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")

    # Liens feuilles de match
    match_links = [
        a.get("href", "")
        for a in soup.find_all("a", href=True)
        if "feuille-de-match" in a.get("href", "") and season in a.get("href", "")
    ]

    # Score-slider pour les infos de base (score, statut)
    matches_data = _extract_vue_prop(soup, "score-slider", ":matches") or []
    matches_by_id = {m["id"]: m for m in matches_data if "id" in m}

    results = []
    for link in match_links:
        # Extraire l'ID match depuis l'URL : /feuille-de-match/2025-2026/j18/11432-toulouse-montauban
        m = re.search(r"/j(\d+)/(\d+)-(.+)$", link)
        if not m:
            continue
        round_num = int(m.group(1))
        match_id = int(m.group(2))
        match_slug = m.group(3)

        score_data = matches_by_id.get(match_id, {})
        score = score_data.get("score", [None, None])

        results.append({
            "season": season,
            "round": round_num,
            "match_id": match_id,
            "match_url": link if link.startswith("http") else LNR_ROUTES.home() + link,
            "team_home": _normalize_team(
                score_data.get("hosting_club", {}).get("name", "")
            ) or match_slug.split("-")[0].replace("-", " ").title(),
            "team_away": _normalize_team(
                score_data.get("visiting_club", {}).get("name", "")
            ) or "",
            "score_home": score[0] if score else None,
            "score_away": score[1] if score else None,
            "status": score_data.get("status", ""),
            "date": score_data.get("date", ""),
        })

    return results


# ---------------------------------------------------------------------------
# Étape 5 : Événements match (pour minutes exactes + scoring events)
# ---------------------------------------------------------------------------

def scrape_match_events(session: RobustSession, match_url: str) -> dict:
    """
    Parse une feuille de match et retourne :
    {
      match_id: int,
      team_home: str,
      team_away: str,
      score_home: int,
      score_away: int,
      game_facts: [{ player_id, player_name, type, subtype, club, minute, period }],
      substitutions: [{ player_in_id, player_out_id, club, minute, type }],
      minutes_by_player: { player_id: total_minutes_played_in_match }
    }
    """
    html = session.get(match_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")

    # Score + équipes
    host_data = _extract_vue_prop(soup, "score-sticky-header", ":hosting-club") or {}
    away_data = _extract_vue_prop(soup, "score-sticky-header", ":visiting-club") or {}

    # Game facts (essais, pénas, conversions, cartons)
    game_facts_raw = _extract_vue_prop(soup, "header-timeline", ":game-facts") or []
    # Timer (pour savoir si le match est terminé)
    timer = _extract_vue_prop(soup, "header-timeline", ":timer") or {}

    # Substitutions (2ème vertical-timeline)
    all_vt = soup.find_all("vertical-timeline")
    subs_raw = []
    if len(all_vt) > 1:
        try:
            subs_raw = json.loads(all_vt[1].get(":items", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

    # Parser les game_facts
    game_facts = []
    for ev in game_facts_raw:
        player = ev.get("player", {}) or {}
        p_url = player.get("url", "")
        p_id = _lnr_id_from_url(p_url)
        p_name = player.get("name", "")
        game_facts.append({
            "player_lnr_id": p_id,
            "player_name": p_name,
            "player_url": p_url,
            "type": ev.get("type", ""),
            "subtype": ev.get("subtype", ""),
            "club": ev.get("club", ""),  # "home" ou "away"
            "minute": ev.get("minute", 0),
            "period": ev.get("period", 0),
            "score_at_event": ev.get("score", []),
        })

    # Parser les substitutions
    substitutions = []
    for sub in subs_raw:
        p_in = sub.get("in", {}) or {}
        p_out = sub.get("out", {}) or {}
        substitutions.append({
            "player_in_lnr_id": _lnr_id_from_url(p_in.get("url", "")),
            "player_in_name": p_in.get("name", ""),
            "player_out_lnr_id": _lnr_id_from_url(p_out.get("url", "")),
            "player_out_name": p_out.get("name", ""),
            "club": sub.get("club", ""),
            "minute": sub.get("minute", 0),
            "type": sub.get("type", ""),  # "Temporaire" ou "Définitif"
        })

    # Calcul minutes jouées par joueur dans ce match
    # (basé sur titulaires 0-80 + remplaçants minute_entrée à 80)
    # Note: sans feuille de composition, on ne peut que déduire depuis les subs
    minutes_by_player = {}
    for sub in substitutions:
        minute = sub["minute"]
        pid_in = sub["player_in_lnr_id"]
        pid_out = sub["player_out_lnr_id"]
        if pid_in:
            minutes_by_player[pid_in] = minutes_by_player.get(pid_in, 0) + (80 - minute)
        if pid_out and pid_out not in minutes_by_player:
            # Le joueur remplacé a joué depuis le début (approximation)
            minutes_by_player[pid_out] = minute

    return {
        "team_home": _normalize_team(host_data.get("name", "")),
        "team_away": _normalize_team(away_data.get("name", "")),
        "match_completed": bool(timer.get("secondPeriodEndDate")),
        "game_facts": game_facts,
        "substitutions": substitutions,
        "minutes_by_player": minutes_by_player,
    }


# ---------------------------------------------------------------------------
# Agrégation des événements match → stats supplémentaires
# ---------------------------------------------------------------------------

def aggregate_match_stats(
    players: list[dict],
    match_events: list[dict],
) -> list[dict]:
    """
    Enrichit chaque joueur avec les stats issues des feuilles de match :
    - points_from_events (essais + conversions + pénalités marquées)
    - yellow_cards_events, red_cards_events
    - Confirmation/correction des minutes depuis les substitutions

    Note: LNR fournit déjà ces totaux dans players-ranking, donc
    c'est une couche de validation / enrichissement.
    """
    # Agréger tous les événements par player_lnr_id
    events_by_player: dict[int, dict] = {}
    for match in match_events:
        for ev in match.get("game_facts", []):
            pid = ev.get("player_lnr_id")
            if not pid:
                continue
            if pid not in events_by_player:
                events_by_player[pid] = {
                    "tries": 0, "penalties_scored": 0, "conversions": 0,
                    "yellow_cards": 0, "red_cards": 0, "orange_cards": 0,
                }
            t, s = ev.get("type", ""), ev.get("subtype", "")
            if t == "Point":
                if s == "Essai":
                    events_by_player[pid]["tries"] += 1
                elif s == "Pénalité":
                    events_by_player[pid]["penalties_scored"] += 1
                elif s == "Transformation":
                    events_by_player[pid]["conversions"] += 1
            elif t == "Exclusion joueur":
                if "rouge" in s.lower():
                    events_by_player[pid]["red_cards"] += 1
                elif "orange" in s.lower():
                    events_by_player[pid]["orange_cards"] += 1
                else:
                    events_by_player[pid]["yellow_cards"] += 1

    # Enrichir les joueurs
    for player in players:
        pid = player.get("lnr_id")
        ev_data = events_by_player.get(pid, {})
        # Ne remplacer que si la source primaire n'a pas la donnée
        if ev_data:
            player["_match_events"] = ev_data  # Pour debug/audit

    return players


# ---------------------------------------------------------------------------
# Calcul des stats /80 min
# ---------------------------------------------------------------------------

def compute_per80(players: list[dict]) -> list[dict]:
    """Calcule les stats /80 minutes depuis les totaux LNR."""
    for p in players:
        minutes_total = p.get("minutes_total") or 0
        if minutes_total <= 0:
            continue

        def per80(total_field: str) -> float | None:
            val = p.get(total_field)
            if val is None:
                return None
            return round(float(val) / minutes_total * 80, 2)

        p["points_scored_per80"] = per80("points_scored_total")
        p["offloads_per80"] = per80("offloads_total")
        p["line_breaks_per80"] = per80("line_breaks_total")
        p["turnovers_won_per80"] = per80("turnovers_won_total")
        # LNR publie uniquement les plaquages réussis (pas le total tentés)
        # → utiliser tackles_success_total comme approximation de tackles_per80
        p["tackles_success_per80"] = per80("tackles_success_total")
        p["tackles_per80"] = p["tackles_success_per80"]  # approx. (réussis seulement)

        # Stats /80 manquantes (seront null, à compléter par Statbunker)
        for field in [
            "tackle_success_pct",
            "penalties_per80", "turnovers_lost_per80",
            "carries_per80", "meters_per80", "passes_per80",
            "kick_meters_per80", "errors_per80",
            "ruck_arrivals_per80", "lineout_wins_per80", "scrum_success_pct",
        ]:
            if field not in p:
                p[field] = None

    return players


# ---------------------------------------------------------------------------
# Pipeline principal LNR
# ---------------------------------------------------------------------------

def run_lnr_pipeline(
    season: str,
    output_path: Path,
    with_profiles: bool = True,
    with_matches: bool = False,
    matches_output_path: Path | None = None,
    min_minutes: int = MIN_MINUTES_THRESHOLD,
) -> list[dict]:
    """
    Pipeline complet :
    1. Récupère la liste des équipes
    2. Pour chaque équipe : stats joueurs (players-ranking)
    3. Pour chaque joueur : profil physique
    4. Calcule les /80 min
    5. Sauvegarde + retourne la liste finale
    """
    session = RobustSession(source_name="LNR", request_delay=2.0)

    # Smoke test saison avant scraping massif (recommandation 1)
    print(f"\n[LNR] Saison : {season}")
    if not season_smoke_test(session, season):
        raise RuntimeError(
            f"Smoke test saison échoué — le site ne renvoie pas la saison {season}. "
            "Vérifier la connectivité ou que la saison existe."
        )

    # Étape 1 : équipes
    teams = scrape_team_list(session)
    if not teams:
        raise RuntimeError("Aucune équipe trouvée — vérifier la connectivité LNR")

    # Étape 2 : stats par équipe
    all_players = []
    match_urls_collected = []
    teams_with_data = []
    teams_not_in_league = []   # clubs présents dans footer mais hors Top14 cette saison

    for team in teams:
        slug = team["slug"]
        canonical = team["name_canonical"]
        if not slug:
            continue

        players = scrape_team_player_stats(session, slug, season, canonical)
        if players:
            all_players.extend(players)
            teams_with_data.append(canonical)
        else:
            # players-ranking vide = probablement hors Top14 cette saison
            teams_not_in_league.append(canonical)

        if with_matches:
            cal = scrape_team_calendar(session, slug, season)
            for m in cal:
                if m.get("match_url") and m["match_url"] not in match_urls_collected:
                    match_urls_collected.append(m["match_url"])

    if teams_not_in_league:
        print(f"[LNR] Clubs exclus (hors Top14 saison {season}) : {teams_not_in_league}")

    n_active = len(teams_with_data)
    print(f"\n[LNR] {len(all_players)} joueurs bruts collectés ({n_active} équipes actives)")

    # Filtrer les joueurs sans temps de jeu minimal
    all_players = [p for p in all_players if (p.get("minutes_total") or 0) >= min_minutes]
    print(f"[LNR] Après filtre {min_minutes} min : {len(all_players)} joueurs")

    # Étape 3 : profils physiques
    if with_profiles:
        print(f"\n[LNR] Chargement profils joueurs...")
        n_enriched = 0
        for i, player in enumerate(all_players):
            if not player.get("_profile_loaded"):
                profile = scrape_player_profile(
                    session, player["lnr_id"], player["lnr_slug"]
                )
                if profile:
                    player.update({k: v for k, v in profile.items() if not player.get(k)})
                    player["_profile_loaded"] = True
                    n_enriched += 1
                if (i + 1) % 50 == 0:
                    print(f"  {i + 1}/{len(all_players)} profils chargés...")

        print(f"  -> {n_enriched} profils enrichis (taille/poids/âge/nationalité)")

    # Étape 4 : Match events (optionnel)
    if with_matches and match_urls_collected:
        print(f"\n[LNR] Parsing {len(match_urls_collected)} feuilles de match...")
        all_events = []
        for j, url in enumerate(match_urls_collected):
            events = scrape_match_events(session, url)
            if events:
                all_events.append(events)
            if (j + 1) % 20 == 0:
                print(f"  {j + 1}/{len(match_urls_collected)} matchs parsés...")

        all_players = aggregate_match_stats(all_players, all_events)

        if matches_output_path:
            with open(matches_output_path, "w", encoding="utf-8") as f:
                json.dump(all_events, f, ensure_ascii=False, indent=2)
            print(f"[OK] {len(all_events)} matchs -> {matches_output_path}")

    # Étape 5 : /80 min
    all_players = compute_per80(all_players)

    # Contrôle nombre d'équipes actives (recommandation 2)
    if n_active < 12:
        print(f"[WARN] Seulement {n_active} équipes avec données (attendu >= 12)")

    # Sauvegarder (avec métadonnées dans le JSON)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_players, f, ensure_ascii=False, indent=2)

    # Sauvegarder métadonnées scraping LNR (pour pipeline_run_metadata.json)
    lnr_meta = {
        "season": season,
        "teams_active": teams_with_data,
        "teams_not_in_league": teams_not_in_league,
        "n_teams_active": n_active,
        "n_players_raw": len(all_players),
        "http_stats": session.stats_summary(),
    }
    meta_path = output_path.parent / "lnr_scrape_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(lnr_meta, f, ensure_ascii=False, indent=2)

    print(f"\n[LNR] Session : {session.stats_summary()}")
    print(f"[OK] {len(all_players)} joueurs -> {output_path}")

    # Rapport de couverture
    _coverage_report(all_players)

    return all_players


def _coverage_report(players: list[dict]):
    """Affiche un rapport de couverture des données."""
    if not players:
        return

    n = len(players)
    fields_to_check = {
        "height_cm": "Taille",
        "weight_kg": "Poids",
        "age": "Âge",
        "nationality": "Nationalité",
        "minutes_total": "Minutes totales",
        "points_scored_total": "Points marqués",
        "tackles_success_total": "Plaquages réussis",
        "offloads_total": "Offloads",
        "line_breaks_total": "Franchissements",
        "turnovers_won_total": "Grattages",
        # Stats manquantes LNR (devraient être toutes None)
        "carries_per80": "Courses/80 (LNR)",
        "meters_per80": "Mètres/80 (LNR)",
    }

    print("\n--- Couverture données LNR ---")
    for field, label in fields_to_check.items():
        count = sum(1 for p in players if p.get(field) is not None)
        pct = count / n * 100
        status = "OK" if pct > 80 else ("WARN" if pct > 20 else "MISSING")
        print(f"  [{status:7s}] {label:30s}: {count:3d}/{n} ({pct:.0f}%)")

    # Par poste
    from collections import Counter
    pos_count = Counter(p["position_group"] for p in players)
    print("\n  Répartition par poste :")
    for pos in ["FRONT_ROW", "LOCK", "BACK_ROW",
                "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK"]:
        print(f"    {pos:12s}: {pos_count.get(pos, 0)}")
    if pos_count.get("UNKNOWN", 0):
        print(f"    UNKNOWN     : {pos_count['UNKNOWN']} <- a corriger dans POSITION_FR_TO_GROUP")


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper LNR Top14 (source officielle)")
    parser.add_argument("--season", default="2023-2024",
                        help="Saison à scraper (ex: 2023-2024)")
    parser.add_argument("--output", default="../raw/lnr_raw.json",
                        help="Fichier de sortie JSON")
    parser.add_argument("--with-matches", action="store_true",
                        help="Parser aussi les feuilles de match")
    parser.add_argument("--matches-output", default="../raw/lnr_matches.json")
    parser.add_argument("--no-profiles", action="store_true",
                        help="Ne pas charger les profils individuels (plus rapide)")
    parser.add_argument("--min-minutes", type=int, default=MIN_MINUTES_THRESHOLD,
                        help="Minutes minimales pour inclure un joueur")
    parser.add_argument("--list-seasons", action="store_true",
                        help="Lister les saisons disponibles")
    parser.add_argument("--test-routes", action="store_true",
                        help="Vérifier les constructeurs d'URL (test unitaire, pas de réseau)")
    args = parser.parse_args()

    if args.test_routes:
        print("\n[Test routes LNR]")
        ok = test_routes()
        sys.exit(0 if ok else 1)

    if args.list_seasons:
        print("Saisons disponibles :")
        for season in SEASON_IDS:
            print(f"  {season}")
        return

    # args.output peut être absolu ou relatif au dossier data/raw/
    raw_dir = Path(__file__).parent.parent / "raw"
    output_path = Path(args.output) if Path(args.output).is_absolute() else (raw_dir / Path(args.output).name)
    output_path = output_path.resolve()
    matches_path = (raw_dir / Path(args.matches_output).name).resolve() if args.with_matches else None

    run_lnr_pipeline(
        season=args.season,
        output_path=output_path,
        with_profiles=not args.no_profiles,
        with_matches=args.with_matches,
        matches_output_path=matches_path,
        min_minutes=args.min_minutes,
    )


if __name__ == "__main__":
    main()
