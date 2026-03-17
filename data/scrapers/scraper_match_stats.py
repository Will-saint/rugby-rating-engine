"""
Scraper Match Stats LNR — données par match pour chaque joueur.

Pour chaque feuille de match 2025-2026 (182 matches Top14),
extrait la page /statistiques-du-match qui contient deux blocs players-ranking
(un par équipe) avec les stats individuelles par match.

Données extraites par joueur par match :
  minutesPlayed, nbPoints, nbEssais, offload, lineBreak, breakdownSteals,
  totalSuccessfulTackles, nbCartonsJaunes, nbCartonsRouges

Utilité :
  - Calcul rolling form (5 derniers matchs)
  - Minutes exactes par match (meilleure précision que la moyenne)
  - Validation croisée avec les totaux saison (club stats)
  - Détection des blessures / absences (0 min ou absent du roster)

Output : data/raw/lnr_match_history.json
  [{"fixture_id", "round", "season", "date", "home_team", "away_team",
    "players": [{"lnr_id", "name", "team", "side", "minutesPlayed", ...}]}]

Usage :
    python data/scrapers/scraper_match_stats.py --season 2025-2026
    python data/scrapers/scraper_match_stats.py --season 2025-2026 --dry-run
    python data/scrapers/scraper_match_stats.py --season 2025-2026 --max 10
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = RAW_DIR / "html_cache"

SITEMAP_URL = "https://top14.lnr.fr/sitemap-game-sheets.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
REQUEST_DELAY = 1.2  # secondes entre requêtes


def get_match_urls(season: str) -> list[str]:
    """Récupère toutes les URLs feuilles-de-match pour une saison depuis le sitemap."""
    r = requests.get(SITEMAP_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    all_urls = re.findall(r"<loc>(.*?)</loc>", r.text)
    return [u for u in all_urls if f"/{season}/" in u
            and "/feuille-de-match/" in u
            and not any(sub in u for sub in ["/statistiques", "/compositions", "/resumes"])]


def _fixture_id_from_url(url: str) -> int | None:
    m = re.search(r"/j\d+/(\d+)-", url)
    return int(m.group(1)) if m else None


def _round_from_url(url: str) -> str:
    m = re.search(r"/(j\d+)/", url)
    return m.group(1) if m else ""


def _teams_from_url(url: str) -> tuple[str, str]:
    """Extrait les slugs équipe depuis l'URL (ex: 11307-clermont-toulouse)."""
    m = re.search(r"/j\d+/\d+-([a-z0-9\-]+)", url)
    if not m:
        return ("", "")
    slug = m.group(1)
    # Le slug est "home-away" mais on ne peut pas toujours splitter proprement
    return slug, ""


def _html_unescape(s: str) -> str:
    import html
    return html.unescape(s)


def fetch_match_stats(fixture_url: str, session: requests.Session) -> dict | None:
    """
    Scrape /statistiques-du-match pour un match.
    Retourne un dict avec les stats des deux équipes, ou None si erreur.
    """
    stats_url = fixture_url.rstrip("/") + "/statistiques-du-match"
    try:
        r = session.get(stats_url, timeout=15)
        if r.status_code != 200:
            return None
    except requests.RequestException as e:
        print(f"  [WARN] {stats_url}: {e}")
        return None

    soup = BeautifulSoup(r.text, "lxml")
    prs = soup.find_all("players-ranking")
    if not prs:
        return None

    # Récupérer le score/header pour identifier les équipes
    ssh = soup.find("score-sticky-header")
    home_name, away_name = "", ""
    if ssh:
        try:
            h_raw = _html_unescape(ssh.get(":hosting-club", "{}"))
            a_raw = _html_unescape(ssh.get(":visiting-club", "{}"))
            home_obj = json.loads(h_raw)
            away_obj = json.loads(a_raw)
            home_name = home_obj.get("name", "")
            away_name = away_obj.get("name", "")
        except Exception:
            pass

    fixture_id = _fixture_id_from_url(fixture_url)
    round_slug = _round_from_url(fixture_url)

    # Timer pour la date
    ht = soup.find("header-timeline")
    match_date = ""
    if ht:
        try:
            timer = json.loads(_html_unescape(ht.get(":timer", "{}")))
            match_date = timer.get("firstPeriodStartDate", "")[:10]  # YYYY-MM-DD
        except Exception:
            pass

    players_data = []
    sides = ["home", "away"]
    team_names = [home_name, away_name]

    for i, pr in enumerate(prs[:2]):
        raw = pr.get(":ranking", "")
        if not raw:
            continue
        try:
            squad = json.loads(_html_unescape(raw))
        except Exception:
            continue

        side = sides[i] if i < len(sides) else f"team_{i}"
        team_name = team_names[i] if i < len(team_names) else ""

        for p in squad:
            player_url = p.get("player", {}).get("url", "")
            m = re.search(r"/joueur/(\d+)-", player_url)
            lnr_id = int(m.group(1)) if m else None
            slug_m = re.search(r"/joueur/\d+-(.+)$", player_url.rstrip("/"))
            lnr_slug = slug_m.group(1) if slug_m else ""

            players_data.append({
                "lnr_id": lnr_id,
                "lnr_slug": lnr_slug,
                "name": p.get("player", {}).get("name", ""),
                "team": team_name,
                "side": side,
                "position_match": p.get("position", ""),
                "minutes_played": int(p.get("minutesPlayed") or 0),
                "points": int(p.get("nbPoints") or 0),
                "tries": int(p.get("nbEssais") or 0),
                "offloads": int(p.get("offload") or 0),
                "line_breaks": int(p.get("lineBreak") or 0),
                "turnovers_won": int(p.get("breakdownSteals") or 0),
                "tackles_success": int(p.get("totalSuccessfulTackles") or 0),
                "yellow_cards": int(p.get("nbCartonsJaunes") or 0),
                "orange_cards": int(p.get("nbCartonsOranges") or 0),
                "red_cards": int(p.get("nbCartonsRouges") or 0),
            })

    return {
        "fixture_id": fixture_id,
        "round": round_slug,
        "season": "",
        "date": match_date,
        "home_team": home_name,
        "away_team": away_name,
        "fixture_url": fixture_url,
        "players": players_data,
    }


def run_match_stats_pipeline(
    season: str,
    output_path: Path,
    max_matches: int = 0,
    dry_run: bool = False,
    verbose: bool = True,
) -> list[dict]:
    """
    Pipeline complet : récupère les stats match par match pour la saison.
    """
    print(f"[Match Stats] Saison {season}")
    urls = get_match_urls(season)
    print(f"[Match Stats] {len(urls)} feuilles-de-match trouvées")

    if max_matches > 0:
        urls = urls[:max_matches]
        print(f"[Match Stats] Limité à {max_matches} matches (--max)")

    if dry_run:
        print("[Match Stats] --dry-run : pas d'écriture")
        return []

    session = requests.Session()
    session.headers.update(HEADERS)

    all_matches = []
    errors = 0

    for i, url in enumerate(urls):
        fixture_id = _fixture_id_from_url(url)
        round_slug = _round_from_url(url)
        if verbose:
            print(f"  [{i+1:3d}/{len(urls)}] {round_slug} #{fixture_id} ... ", end="", flush=True)

        result = fetch_match_stats(url, session)
        if result:
            result["season"] = season
            all_matches.append(result)
            n_players = len(result["players"])
            if verbose:
                print(f"{result['home_team']} vs {result['away_team']} | {n_players} joueurs")
        else:
            errors += 1
            if verbose:
                print("ERREUR")

        if i < len(urls) - 1:
            time.sleep(REQUEST_DELAY)

    print(f"\n[Match Stats] {len(all_matches)} matches OK, {errors} erreurs")

    if all_matches:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_matches, f, ensure_ascii=False, indent=2)
        print(f"[OK] {output_path}")

        # Résumé
        total_player_records = sum(len(m["players"]) for m in all_matches)
        print(f"[Match Stats] {total_player_records} entrées joueur-match")

    return all_matches


def print_summary(matches: list[dict]) -> None:
    """Affiche un résumé de la couverture des match stats."""
    from collections import defaultdict

    player_stats: dict[int, dict] = defaultdict(lambda: {
        "name": "", "team": "", "matches": 0,
        "minutes": 0, "tackles": 0, "line_breaks": 0,
    })

    for m in matches:
        for p in m["players"]:
            pid = p["lnr_id"] or 0
            ps = player_stats[pid]
            ps["name"] = p["name"]
            ps["team"] = p["team"]
            ps["matches"] += 1
            ps["minutes"] += p["minutes_played"]
            ps["tackles"] += p["tackles_success"]
            ps["line_breaks"] += p["line_breaks"]

    print(f"\nJoueurs uniques trackés : {len(player_stats)}")
    # Top plaqueurs agrégés depuis les feuilles de match
    top = sorted(player_stats.values(), key=lambda x: x["tackles"], reverse=True)[:10]
    print("\nTop plaqueurs (agrégé match sheets):")
    for p in top:
        print(f"  {p['name']:25s} {p['team']:15s} {p['tackles']:4d} tackles en {p['matches']} matchs")


def main():
    parser = argparse.ArgumentParser(description="Scraper Match Stats LNR")
    parser.add_argument("--season", default="2025-2026")
    parser.add_argument("--output", default=None)
    parser.add_argument("--max", type=int, default=0,
                        help="Nombre max de matches à scraper (0 = tous)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary", action="store_true",
                        help="Afficher résumé depuis fichier existant")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else RAW_DIR / "lnr_match_history.json"

    if args.summary and output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            matches = json.load(f)
        print_summary(matches)
        return

    matches = run_match_stats_pipeline(
        season=args.season,
        output_path=output_path,
        max_matches=args.max,
        dry_run=args.dry_run,
    )

    if matches:
        print_summary(matches)


if __name__ == "__main__":
    main()
