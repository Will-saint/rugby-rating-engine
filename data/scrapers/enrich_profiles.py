"""
Enrichit lnr_raw.json avec taille, poids, âge, nationalité
en scrapant les pages profil LNR pour les joueurs sans données.

Usage :
    python data/scrapers/enrich_profiles.py             # nouveaux joueurs uniquement
    python data/scrapers/enrich_profiles.py --retry     # réessaye les échecs précédents
    python data/scrapers/enrich_profiles.py --all       # force tous (ignore _profile_loaded)
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from http_client import RobustSession
from scraper_lnr import scrape_player_profile

RAW_PATH = Path(__file__).parent.parent / "raw" / "lnr_raw.json"
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # secondes entre tentatives sur échec


def _try_profile(session, lnr_id: int, slug: str, max_retries: int = MAX_RETRIES) -> dict | None:
    for attempt in range(1, max_retries + 1):
        try:
            result = scrape_player_profile(session, lnr_id, slug)
            if result:
                return result
        except Exception as e:
            pass
        if attempt < max_retries:
            time.sleep(RETRY_DELAY * attempt)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry", action="store_true", help="Réessaye les joueurs marqués _profile_failed")
    parser.add_argument("--all", action="store_true", help="Force le re-scraping de tous les joueurs")
    args = parser.parse_args()

    with open(RAW_PATH, encoding="utf-8") as f:
        players = json.load(f)

    if args.all:
        need_profile = [p for p in players if p.get("lnr_id") and p.get("lnr_slug")]
        print(f"Mode --all : {len(need_profile)} joueurs à traiter")
    elif args.retry:
        need_profile = [p for p in players if p.get("_profile_failed") and p.get("lnr_id")]
        print(f"Mode --retry : {len(need_profile)} joueurs en échec à réessayer")
    else:
        need_profile = [
            p for p in players
            if not p.get("_profile_loaded") and not p.get("_profile_failed")
            and p.get("lnr_id") and p.get("lnr_slug")
        ]
        print(f"Joueurs sans profil : {len(need_profile)} / {len(players)}")

    failed_prev = sum(1 for p in players if p.get("_profile_failed"))
    if failed_prev and not args.retry:
        print(f"  (+ {failed_prev} en échec précédent — lance --retry pour les réessayer)")

    if not need_profile:
        print("Rien à faire.")
        return

    session = RobustSession(source_name="enrich_profiles", request_delay=0.5)
    updated = 0
    failed = 0

    for i, player in enumerate(need_profile, 1):
        lnr_id = int(float(player["lnr_id"]))
        slug = player["lnr_slug"]
        print(f"[{i}/{len(need_profile)}] {player['name']} ({slug})", end=" ... ", flush=True)

        profile = _try_profile(session, lnr_id, slug)
        if profile:
            player.update(profile)
            player["_profile_loaded"] = True
            player.pop("_profile_failed", None)  # efface l'échec précédent si ça marche
            updated += 1
            parts = []
            if profile.get("height_cm"):
                parts.append(f"{profile['height_cm']}cm")
            if profile.get("weight_kg"):
                parts.append(f"{profile['weight_kg']}kg")
            if profile.get("age"):
                parts.append(f"{profile['age']}ans")
            if profile.get("nationality"):
                parts.append(profile["nationality"])
            print(", ".join(parts) if parts else "vide")
        else:
            # Ne pas marquer _profile_loaded — sera réessayé avec --retry
            player["_profile_failed"] = True
            player.pop("_profile_loaded", None)
            failed += 1
            print("ÉCHEC (sera réessayé avec --retry)")

        # Sauvegarde incrémentale toutes les 50 requêtes
        if i % 50 == 0:
            with open(RAW_PATH, "w", encoding="utf-8") as f:
                json.dump(players, f, ensure_ascii=False, indent=2)
            print(f"  >>> Sauvegarde intermédiaire ({updated} ok, {failed} échecs)")

    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé : {updated} enrichis, {failed} échecs")
    if failed:
        print(f"  → Lance 'python enrich_profiles.py --retry' pour réessayer les {failed} échecs")
    print(f"Fichier mis à jour : {RAW_PATH}")


if __name__ == "__main__":
    main()
