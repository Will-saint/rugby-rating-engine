"""
Télécharge les photos des joueurs stars depuis Wikipedia.
Usage : python data/download_photos.py
"""

import os
import sys
import time
import urllib.request
import urllib.parse
import json

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

# Joueurs stars : (nom fichier, terme de recherche Wikipedia)
STAR_PLAYERS = [
    ("Antoine Dupont",       "Antoine Dupont rugby"),
    ("Romain Ntamack",       "Romain Ntamack"),
    ("Thomas Ramos",         "Thomas Ramos rugby union"),
    ("Julien Marchand",      "Julien Marchand rugby"),
    ("Cyril Baille",         "Cyril Baille"),
    ("Francois Cros",        "François Cros"),
    ("Gregory Alldritt",     "Grégory Alldritt"),
    ("Uini Atonio",          "Uini Atonio"),
    ("Brice Dulin",          "Brice Dulin"),
    ("Pierre Bourgarit",     "Pierre Bourgarit"),
    ("Matthieu Jalibert",    "Matthieu Jalibert"),
    ("Damian Penaud",        "Damian Penaud"),
    ("Cameron Woki",         "Cameron Woki"),
    ("Gael Fickou",          "Gaël Fickou"),
    ("Jonathan Danty",       "Jonathan Danty"),
    ("Finn Russell",         "Finn Russell rugby"),
    ("Will Skelton",         "Will Skelton"),
    ("Peceli Yato",          "Peceli Yato"),
    ("Emmanuel Meafou",      "Emmanuel Meafou"),
    ("Louis Carbonel",       "Louis Carbonel"),
    ("Charles Ollivon",      "Charles Ollivon"),
    ("Gabin Villiere",       "Gabin Villiere"),
    ("Cobus Reinach",        "Cobus Reinach"),
    ("Paolo Garbisi",        "Paolo Garbisi"),
    ("Zach Mercer",          "Zach Mercer rugby"),
    ("Melvyn Jaminet",       "Melvyn Jaminet"),
    ("Baptiste Couilloud",   "Baptiste Couilloud"),
    ("Dylan Cretin",         "Dylan Cretin"),
    ("Ben Lam",              "Ben Lam rugby"),
]

HEADERS = {
    "User-Agent": "RugbyRatingEngine/1.0 (educational project)",
    "Accept": "application/json",
}


def search_wikipedia_image(query: str) -> str | None:
    """Retourne l'URL de l'image principale de la page Wikipedia la plus pertinente."""
    # Étape 1 : recherche
    search_url = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&list=search&srsearch="
        + urllib.parse.quote(query)
        + "&srlimit=1&format=json"
    )
    try:
        req = urllib.request.Request(search_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        results = data.get("query", {}).get("search", [])
        if not results:
            return None
        page_title = results[0]["title"]
    except Exception as e:
        print(f"    Erreur recherche : {e}")
        return None

    # Étape 2 : image principale de la page
    img_url = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&prop=pageimages&pithumbsize=400"
        "&titles=" + urllib.parse.quote(page_title)
        + "&format=json"
    )
    try:
        req = urllib.request.Request(img_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb.get("source"):
                return thumb["source"]
    except Exception as e:
        print(f"    Erreur image : {e}")
    return None


def download_image(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        # Vérifier que c'est bien une image
        if len(data) < 1000:
            return False
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"    Erreur téléchargement : {e}")
        return False


def main():
    ok, skip, fail = 0, 0, 0
    for name, query in STAR_PLAYERS:
        dest = os.path.join(PHOTOS_DIR, f"{name}.jpg")
        if os.path.exists(dest):
            print(f"  [SKIP] {name} — déjà téléchargée")
            skip += 1
            continue

        print(f"  [{name}] recherche sur Wikipedia...")
        img_url = search_wikipedia_image(query)
        if not img_url:
            print(f"    -> Aucune image trouvée")
            fail += 1
        else:
            success = download_image(img_url, dest)
            if success:
                size_kb = os.path.getsize(dest) // 1024
                print(f"    -> OK ({size_kb} KB)")
                ok += 1
            else:
                fail += 1
        time.sleep(2.0)  # Respecter le rate limit Wikipedia

    print(f"\nTermine : {ok} telecharges, {skip} deja presents, {fail} echecs")
    print(f"Dossier : {PHOTOS_DIR}")


if __name__ == "__main__":
    main()
