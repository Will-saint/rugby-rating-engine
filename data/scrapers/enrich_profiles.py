"""
Enrichit lnr_raw.json avec taille, poids, âge, nationalité
en scrapant les pages profil LNR pour les joueurs sans données.

Usage : python data/scrapers/enrich_profiles.py
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from http_client import RobustSession
from scraper_lnr import scrape_player_profile

RAW_PATH = Path(__file__).parent.parent / "raw" / "lnr_raw.json"


def main():
    with open(RAW_PATH, encoding="utf-8") as f:
        players = json.load(f)

    need_profile = [
        p for p in players
        if not p.get("_profile_loaded") and p.get("lnr_id") and p.get("lnr_slug")
    ]
    print(f"Joueurs sans profil : {len(need_profile)} / {len(players)}")

    if not need_profile:
        print("Tous les profils sont déjà chargés.")
        return

    session = RobustSession(source_name="enrich_profiles", request_delay=0.5)
    updated = 0

    for i, player in enumerate(need_profile, 1):
        lnr_id = int(float(player["lnr_id"]))
        slug = player["lnr_slug"]
        print(f"[{i}/{len(need_profile)}] {player['name']} ({slug})", end=" ... ", flush=True)

        profile = scrape_player_profile(session, lnr_id, slug)
        if profile:
            player.update(profile)
            player["_profile_loaded"] = True
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
            player["_profile_loaded"] = True  # évite de re-tenter
            print("échec")

        # Sauvegarde incrémentale toutes les 50 requêtes
        if i % 50 == 0:
            with open(RAW_PATH, "w", encoding="utf-8") as f:
                json.dump(players, f, ensure_ascii=False, indent=2)
            print(f"  >>> Sauvegarde intermédiaire ({updated} profils)")

    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé : {updated}/{len(need_profile)} profils enrichis")
    print(f"Fichier mis à jour : {RAW_PATH}")


if __name__ == "__main__":
    main()
