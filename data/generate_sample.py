"""
Générateur de données joueurs synthétiques mais réalistes.
Produit : data/players.csv

Usage : python data/generate_sample.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

np.random.seed(42)

# ---------------------------------------------------------------------------
# Distributions réalistes par poste (mean, std, min, max) pour chaque stat
# ---------------------------------------------------------------------------
DISTRIBUTIONS = {
    "FRONT_ROW": {
        # Piliers (1,3) + Talonneur (2) — stats moyennées
        "tackles_per80":        (8.8,  2.5, 3,   17),
        "tackle_success_pct":   (82,   6,   65,  96),
        "penalties_per80":      (1.9,  0.7, 0.2, 4.0),
        "turnovers_won_per80":  (0.7,  0.5, 0,   2.5),
        "turnovers_lost_per80": (0.5,  0.3, 0,   1.5),
        "carries_per80":        (9.5,  3,   3,   18),
        "meters_per80":         (27,   10,  8,   55),
        "line_breaks_per80":    (0.15, 0.2, 0,   0.7),
        "offloads_per80":       (0.45, 0.4, 0,   1.5),
        "passes_per80":         (7,    3,   2,   15),
        "kick_meters_per80":    (5,    6,   0,   22),
        "points_scored_per80":  (0.3,  0.5, 0,   2.0),
        "errors_per80":         (0.85, 0.5, 0,   2.5),
        "ruck_arrivals_per80":  (11.5, 4,   4,   22),
        "lineout_wins_per80":   (2.1,  1.5, 0,   7.5),
        "scrum_success_pct":    (77,   12,  48,  99),
    },
    "LOCK": {
        "tackles_per80":        (9,    2.5, 4,   17),
        "tackle_success_pct":   (83,   6,   66,  96),
        "penalties_per80":      (1.5,  0.7, 0.2, 3.5),
        "turnovers_won_per80":  (0.7,  0.5, 0,   2.0),
        "turnovers_lost_per80": (0.4,  0.3, 0,   1.3),
        "carries_per80":        (9,    3,   3,   17),
        "meters_per80":         (32,   12,  10,  60),
        "line_breaks_per80":    (0.2,  0.2, 0,   0.8),
        "offloads_per80":       (0.5,  0.4, 0,   1.5),
        "passes_per80":         (6,    3,   1,   14),
        "kick_meters_per80":    (4,    5,   0,   18),
        "points_scored_per80":  (0.2,  0.4, 0,   1.8),
        "errors_per80":         (0.7,  0.5, 0,   2.0),
        "ruck_arrivals_per80":  (14,   4,   6,   24),
        "lineout_wins_per80":   (3.5,  1.5, 1.0, 7.0),
        "scrum_success_pct":    (72,   15,  45,  98),
    },
    "BACK_ROW": {
        # Flankers (6,7) + Numéro 8 — stats moyennées
        "tackles_per80":        (11,   3,   5,   22),
        "tackle_success_pct":   (84,   5,   70,  97),
        "penalties_per80":      (1.7,  0.7, 0.2, 3.8),
        "turnovers_won_per80":  (1.35, 0.65,0.2, 3.5),
        "turnovers_lost_per80": (0.45, 0.3, 0,   1.5),
        "carries_per80":        (11,   3.5, 4,   22),
        "meters_per80":         (40,   14,  12,  80),
        "line_breaks_per80":    (0.4,  0.35,0,   1.8),
        "offloads_per80":       (0.85, 0.5, 0,   2.5),
        "passes_per80":         (6.5,  3,   1,   15),
        "kick_meters_per80":    (5.5,  6.5, 0,   25),
        "points_scored_per80":  (0.35, 0.5, 0,   2.0),
        "errors_per80":         (0.7,  0.4, 0,   2.0),
        "ruck_arrivals_per80":  (12.5, 4,   5,   23),
        "lineout_wins_per80":   (0.3,  0.4, 0,   1.5),
        "scrum_success_pct":    (72,   15,  45,  95),
    },
    "SCRUM_HALF": {
        "tackles_per80":        (7,    2.5, 3,   14),
        "tackle_success_pct":   (80,   7,   62,  95),
        "penalties_per80":      (1.5,  0.6, 0.2, 3.2),
        "turnovers_won_per80":  (0.6,  0.4, 0,   1.8),
        "turnovers_lost_per80": (0.8,  0.5, 0.1, 2.5),
        "carries_per80":        (6,    2.5, 2,   13),
        "meters_per80":         (22,   10,  8,   48),
        "line_breaks_per80":    (0.4,  0.4, 0,   1.5),
        "offloads_per80":       (0.4,  0.4, 0,   1.5),
        "passes_per80":         (35,   10,  15,  60),
        "kick_meters_per80":    (45,   20,  10,  100),
        "points_scored_per80":  (0.5,  0.6, 0,   2.5),
        "errors_per80":         (0.6,  0.4, 0,   2.0),
        "ruck_arrivals_per80":  (5,    3,   1,   12),
        "lineout_wins_per80":   (0.2,  0.3, 0,   1.0),
        "scrum_success_pct":    (75,   15,  50,  98),
    },
    "FLY_HALF": {
        "tackles_per80":        (5,    2,   1,   10),
        "tackle_success_pct":   (76,   8,   55,  93),
        "penalties_per80":      (1.4,  0.6, 0.1, 3.0),
        "turnovers_won_per80":  (0.5,  0.4, 0,   1.5),
        "turnovers_lost_per80": (0.7,  0.5, 0,   2.0),
        "carries_per80":        (7,    2.5, 2,   14),
        "meters_per80":         (35,   14,  10,  70),
        "line_breaks_per80":    (0.4,  0.4, 0,   1.5),
        "offloads_per80":       (0.5,  0.4, 0,   1.5),
        "passes_per80":         (20,   7,   8,   38),
        "kick_meters_per80":    (110,  40,  40,  210),
        "points_scored_per80":  (5,    3,   0,   14),
        "errors_per80":         (0.7,  0.5, 0,   2.2),
        "ruck_arrivals_per80":  (3,    2,   0,   8),
        "lineout_wins_per80":   (0.1,  0.2, 0,   0.6),
        "scrum_success_pct":    (70,   15,  45,  95),
    },
    "WINGER": {
        "tackles_per80":        (5,    2.5, 1,   12),
        "tackle_success_pct":   (79,   8,   58,  95),
        "penalties_per80":      (1.0,  0.5, 0.1, 2.5),
        "turnovers_won_per80":  (0.5,  0.4, 0,   1.5),
        "turnovers_lost_per80": (0.7,  0.5, 0.1, 2.0),
        "carries_per80":        (9,    3,   3,   17),
        "meters_per80":         (70,   25,  25,  140),
        "line_breaks_per80":    (1.0,  0.7, 0.1, 3.0),
        "offloads_per80":       (0.5,  0.4, 0,   1.8),
        "passes_per80":         (6,    3,   1,   14),
        "kick_meters_per80":    (15,   15,  0,   55),
        "points_scored_per80":  (1.2,  0.8, 0,   4.0),
        "errors_per80":         (0.8,  0.5, 0,   2.5),
        "ruck_arrivals_per80":  (4,    2.5, 0,   10),
        "lineout_wins_per80":   (0.1,  0.2, 0,   0.5),
        "scrum_success_pct":    (68,   15,  40,  90),
    },
    "CENTRE": {
        "tackles_per80":        (8,    2.5, 3,   16),
        "tackle_success_pct":   (82,   6,   65,  96),
        "penalties_per80":      (1.3,  0.6, 0.1, 3.0),
        "turnovers_won_per80":  (0.6,  0.4, 0,   1.8),
        "turnovers_lost_per80": (0.7,  0.5, 0.1, 2.2),
        "carries_per80":        (10,   3,   4,   19),
        "meters_per80":         (60,   20,  20,  115),
        "line_breaks_per80":    (0.7,  0.5, 0.1, 2.0),
        "offloads_per80":       (0.8,  0.5, 0,   2.2),
        "passes_per80":         (12,   4,   4,   22),
        "kick_meters_per80":    (20,   15,  0,   60),
        "points_scored_per80":  (0.8,  0.7, 0,   3.0),
        "errors_per80":         (0.7,  0.4, 0,   2.0),
        "ruck_arrivals_per80":  (6,    3,   1,   13),
        "lineout_wins_per80":   (0.1,  0.2, 0,   0.6),
        "scrum_success_pct":    (68,   15,  40,  90),
    },
    "FULLBACK": {
        "tackles_per80":        (5,    2,   1,   11),
        "tackle_success_pct":   (80,   7,   60,  95),
        "penalties_per80":      (1.1,  0.5, 0.1, 2.5),
        "turnovers_won_per80":  (0.4,  0.4, 0,   1.5),
        "turnovers_lost_per80": (0.6,  0.4, 0.1, 1.8),
        "carries_per80":        (8,    3,   2,   16),
        "meters_per80":         (80,   25,  30,  150),
        "line_breaks_per80":    (1.0,  0.7, 0.1, 3.0),
        "offloads_per80":       (0.6,  0.4, 0,   1.8),
        "passes_per80":         (10,   4,   3,   20),
        "kick_meters_per80":    (70,   30,  20,  150),
        "points_scored_per80":  (1.0,  0.8, 0,   4.0),
        "errors_per80":         (0.7,  0.4, 0,   2.0),
        "ruck_arrivals_per80":  (3,    2,   0,   8),
        "lineout_wins_per80":   (0.1,  0.2, 0,   0.5),
        "scrum_success_pct":    (68,   15,  40,  90),
    },
}

# ---------------------------------------------------------------------------
# Équipes Top 14
# ---------------------------------------------------------------------------
TEAMS = [
    ("Stade Toulousain",  "TLS"),
    ("Bordeaux-Begles",   "UBB"),
    ("Stade Rochelais",   "SRT"),
    ("Racing 92",         "R92"),
    ("ASM Clermont",      "ASM"),
    ("Stade Francais",    "SFP"),
    ("RC Toulon",         "RCT"),
    ("LOU Rugby",         "LOU"),
    ("Castres Olympique", "CO"),
    ("Montpellier HRC",   "MHR"),
    ("USAP Perpignan",    "USAP"),
    ("Aviron Bayonnais",  "BAY"),
    ("CA Brive",          "CAB"),
    ("Section Paloise",   "SP"),
]

# Mapping position numéro → (nom, groupe)
POSITION_MAP = {
    1:  ("Pilier Gauche",     "FRONT_ROW"),
    2:  ("Talonneur",         "FRONT_ROW"),
    3:  ("Pilier Droit",      "FRONT_ROW"),
    4:  ("2ème Ligne",        "LOCK"),
    5:  ("2ème Ligne",        "LOCK"),
    6:  ("Flanker Aveugle",   "BACK_ROW"),
    7:  ("Flanker Ouvert",    "BACK_ROW"),
    8:  ("Numéro 8",          "BACK_ROW"),
    9:  ("Demi de Mêlée",     "SCRUM_HALF"),
    10: ("Ouvreur",           "FLY_HALF"),
    11: ("Ailier Gauche",     "WINGER"),
    12: ("Centre Int.",       "CENTRE"),
    13: ("Centre Ext.",       "CENTRE"),
    14: ("Ailier Droit",      "WINGER"),
    15: ("Arrière",           "FULLBACK"),
}

# Nationalités avec probabilités
NATIONALITIES = [
    ("France", 0.55), ("New Zealand", 0.06), ("South Africa", 0.06),
    ("Australia", 0.04), ("Argentina", 0.04), ("Fiji", 0.05),
    ("England", 0.04), ("Ireland", 0.03), ("Scotland", 0.02),
    ("Wales", 0.02), ("Tonga", 0.03), ("Samoa", 0.03),
    ("Italy", 0.02), ("Georgia", 0.01),
]
NAT_NAMES, NAT_PROBS = zip(*NATIONALITIES)
NAT_PROBS = np.array(NAT_PROBS)
NAT_PROBS = NAT_PROBS / NAT_PROBS.sum()

# ---------------------------------------------------------------------------
# Prénoms / noms par nationalité
# ---------------------------------------------------------------------------
FIRST_NAMES = {
    "France": ["Antoine", "Romain", "Thomas", "Matthieu", "François", "Damian",
               "Grégory", "Julien", "Hugo", "Gaël", "Jonathan", "Baptiste",
               "Louis", "Maxime", "Florian", "Théo", "Lucas", "Clément",
               "Adrien", "Pierre", "Nicolas", "Alexandre", "Quentin", "Paul"],
    "New Zealand": ["Richie", "Beauden", "Ardie", "Scott", "Sam", "Brodie",
                    "Anton", "Jordie", "TJ", "Dane", "Will", "Aaron"],
    "South Africa": ["Eben", "Duane", "Pieter", "Faf", "Handre", "Cheslin",
                     "Makazole", "Sbu", "Kwagga", "Malcolm"],
    "Australia": ["Will", "James", "Michael", "David", "Tom", "Jack",
                  "Ben", "Jordan", "Hunter", "Andrew"],
    "Argentina": ["Nicolas", "Tomas", "Rodrigo", "Pablo", "Juan", "Marcos",
                  "Matias", "Santiago", "Jeronimo", "Emiliano"],
    "Fiji": ["Semi", "Josua", "Waisea", "Levani", "Nemani", "Peceli",
             "Campese", "Leone", "Mosese"],
    "England": ["Owen", "George", "Henry", "Tom", "Ben", "Ellis",
                "Sam", "Jack", "Harry", "Charlie"],
    "Ireland": ["Johnny", "Cian", "Tadhg", "Keith", "James", "Peter",
                "Rob", "Ronan", "Brian", "Conor"],
    "Scotland": ["Finn", "Stuart", "Ali", "Gordon", "Jim", "Greig",
                 "Pete", "Duncan", "Magnus"],
    "Wales": ["Alun", "Taulupe", "Toby", "Liam", "George", "Gareth",
              "Scott", "Dafydd", "Ioan"],
    "Tonga": ["Charles", "Siale", "Vunipola", "Nili", "Mako", "Billy"],
    "Samoa": ["TJ", "Rey", "Logovi'i", "Ti'i", "Lima", "Steven"],
    "Italy": ["Andrea", "Sergio", "Edoardo", "Federico", "Luca", "Marco"],
    "Georgia": ["Merab", "Giorgi", "Lasha", "Shalva", "Davit"],
}

LAST_NAMES = {
    "France": ["Dupont", "Martin", "Bernard", "Thomas", "Robert", "Richard",
               "Petit", "Durand", "Leroy", "Moreau", "Simon", "Laurent",
               "Lefebvre", "Michel", "Garcia", "David", "Bertrand", "Roux",
               "Vincent", "Fournier", "Morel", "Girard", "Andre", "Blanc",
               "Guerin", "Robin", "Bonnet", "Mercier", "Perez", "Lambert"],
    "New Zealand": ["McCaw", "Carter", "Smith", "Read", "Retallick", "Cane",
                    "Barrett", "Savea", "Dagg", "Fekitoa", "Taylor"],
    "South Africa": ["Etzebeth", "Vermeulen", "Kolisi", "De Klerk", "Pollard",
                     "Am", "Mapimpi", "Nkosi", "Snyman", "Mostert"],
    "Australia": ["Hooper", "Pocock", "Beale", "Foley", "Phipps",
                  "Kuridrani", "Speight", "Genia", "Leali'ifano"],
    "Argentina": ["Fernandez", "Sanchez", "Creevy", "Petti", "Lavanini",
                  "Isa", "Tuculet", "Moroni", "De la Fuente", "Landajo"],
    "Fiji": ["Radradra", "Tuisova", "Mata", "Nadolo", "Tagitagivalu",
             "Yato", "Ma'afu", "Aca", "Goneva"],
    "England": ["Farrell", "Itoje", "Vunipola", "Ford", "May",
                "Watson", "Brown", "Curry", "Launchbury", "Hill"],
    "Ireland": ["Sexton", "Murray", "Healy", "Furlong", "O'Brien",
                "O'Mahony", "Schmidt", "Henderson", "Earls", "Henshaw"],
    "Scotland": ["Russell", "Watson", "Gilchrist", "Gray", "Hardie",
                 "Nel", "White", "Price", "Huw", "Ritchie"],
    "Wales": ["Faletau", "Davies", "Biggar", "North", "Anscombe",
              "Halfpenny", "Adams", "Tipuric", "Alun Wyn"],
    "Tonga": ["Vunipola", "Tuilagi", "Ma'afu", "Piutau", "Lolohea"],
    "Samoa": ["Lima", "Tuilagi", "Fono", "Pisi", "Stanley"],
    "Italy": ["Parisse", "Zanni", "Minozzi", "Canna", "Padovani", "Negri"],
    "Georgia": ["Gorgodze", "Nariashvili", "Sharikadze", "Lobzhanidze"],
}


def gen_name(nat: str) -> str:
    first = np.random.choice(FIRST_NAMES.get(nat, ["Alex"]))
    last = np.random.choice(LAST_NAMES.get(nat, ["Martin"]))
    return f"{first} {last}"


# Stats où moins = mieux (boost = réduction pour les stars)
NEGATIVE_STATS = {"penalties_per80", "turnovers_lost_per80", "errors_per80"}


def gen_stats(pg: str, boost: float = 0.0) -> dict:
    """Génère des stats pour un joueur du groupe de poste pg, avec un boost optionnel (joueur star).
    Le boost améliore les stats positives et réduit les stats négatives (discipline).
    """
    dist = DISTRIBUTIONS[pg]
    stats = {}
    for stat, (mean, std, lo, hi) in dist.items():
        # Pour les stats négatives : boost réduit la valeur (moins de fautes)
        direction = -1 if stat in NEGATIVE_STATS else 1
        val = np.random.normal(mean + direction * boost * std * 0.5, std * 0.8)
        val = float(np.clip(val, lo, hi))
        # Arrondi à 1 décimale sauf pourcentages
        if "pct" in stat:
            val = round(val, 1)
        else:
            val = round(val, 2)
        stats[stat] = val
    return stats


def gen_physical(pg: str) -> dict:
    physicals = {
        "FRONT_ROW": {"height_cm": (182, 3, 172, 193), "weight_kg": (112, 8, 95,  135)},
        "LOCK":      {"height_cm": (200, 4, 192, 210), "weight_kg": (118, 8, 102, 138)},
        "BACK_ROW":  {"height_cm": (191, 4, 182, 203), "weight_kg": (110, 8, 95,  128)},
        "SCRUM_HALF":{"height_cm": (176, 4, 168, 186), "weight_kg": (85,  7, 75,  100)},
        "FLY_HALF":  {"height_cm": (182, 4, 172, 192), "weight_kg": (90,  7, 80,  106)},
        "WINGER":    {"height_cm": (183, 5, 173, 195), "weight_kg": (90,  7, 80,  106)},
        "CENTRE":    {"height_cm": (185, 5, 175, 197), "weight_kg": (95,  7, 83,  110)},
        "FULLBACK":  {"height_cm": (183, 5, 173, 195), "weight_kg": (90,  7, 80,  106)},
    }
    result = {}
    for key, (m, s, lo, hi) in physicals[pg].items():
        result[key] = int(np.clip(np.random.normal(m, s), lo, hi))
    return result


# ---------------------------------------------------------------------------
# Joueurs stars avec stats pré-définies (légèrement boostées)
# ---------------------------------------------------------------------------
STAR_PLAYERS = [
    # (nom, poste_num, équipe, nationalité, boost)
    ("Antoine Dupont",     9,  "Stade Toulousain",  "France",       2.5),
    ("Romain Ntamack",    10,  "Stade Toulousain",  "France",       2.0),
    ("Thomas Ramos",      15,  "Stade Toulousain",  "France",       1.8),
    ("Julien Marchand",    2,  "Stade Toulousain",  "France",       1.5),
    ("Cyril Baille",       1,  "Stade Toulousain",  "France",       1.6),
    ("Francois Cros",      6,  "Stade Toulousain",  "France",       1.7),
    ("Gregory Alldritt",   8,  "Stade Rochelais",   "France",       2.2),
    ("Uini Atonio",        3,  "Stade Rochelais",   "France",       1.6),
    ("Brice Dulin",       15,  "Stade Rochelais",   "France",       1.5),
    ("Pierre Bourgarit",   2,  "Stade Rochelais",   "France",       1.5),
    ("Matthieu Jalibert", 10,  "Bordeaux-Begles",   "France",       1.9),
    ("Damian Penaud",     11,  "Bordeaux-Begles",   "France",       2.0),
    ("Cameron Woki",       6,  "Bordeaux-Begles",   "France",       1.7),
    ("Dany Priso",         3,  "Bordeaux-Begles",   "France",       1.4),
    ("Gael Fickou",       13,  "Stade Francais",    "France",       1.8),
    ("Jonathan Danty",    12,  "Stade Francais",    "France",       1.5),
    ("Finn Russell",      10,  "Racing 92",         "Scotland",     1.9),
    ("Will Skelton",       5,  "Stade Rochelais",   "Australia",    1.8),
    ("Peceli Yato",        8,  "Bordeaux-Begles",   "Fiji",         1.6),
    ("Emmanuel Meafou",    5,  "Stade Toulousain",  "Argentina",    1.7),
    # RC Toulon
    ("Louis Carbonel",    10,  "RC Toulon",         "France",       1.7),
    ("Charles Ollivon",    6,  "RC Toulon",         "France",       1.8),
    ("Gabin Villiere",    14,  "RC Toulon",         "France",       1.6),
    # ASM Clermont
    ("Irae Simone",       12,  "ASM Clermont",      "Australia",    1.5),
    ("Etienne Falgoux",    1,  "ASM Clermont",      "France",       1.4),
    # LOU Rugby
    ("Baptiste Couilloud", 9,  "LOU Rugby",         "France",       1.6),
    ("Dylan Cretin",       8,  "LOU Rugby",         "France",       1.5),
    # Castres Olympique
    ("Pierre-Henri Azagoh",2,  "Castres Olympique", "France",       1.3),
    ("Josaia Raisuqe",    11,  "Castres Olympique", "Fiji",         1.5),
    # Montpellier HRC
    ("Cobus Reinach",      9,  "Montpellier HRC",   "South Africa", 1.7),
    ("Paolo Garbisi",     10,  "Montpellier HRC",   "Italy",        1.6),
    ("Zach Mercer",        8,  "Montpellier HRC",   "England",      1.7),
    # USAP Perpignan
    ("Melvyn Jaminet",    15,  "USAP Perpignan",    "France",       1.6),
    ("Thibault Debaes",    4,  "USAP Perpignan",    "France",       1.3),
    # Aviron Bayonnais
    ("Yann Lesgourgues",   9,  "Aviron Bayonnais",  "France",       1.4),
    ("Kane Douglas",       5,  "Aviron Bayonnais",  "Australia",    1.4),
    # CA Brive
    ("Ioani Lapandry",     7,  "CA Brive",          "France",       1.3),
    ("Ben Lam",           11,  "CA Brive",          "New Zealand",  1.5),
    # Section Paloise
    ("Lucas Dubourdieau", 10,  "Section Paloise",   "France",       1.4),
    ("Masivesi Dakuwaqa", 14,  "Section Paloise",   "Fiji",         1.5),
]


def generate_players() -> pd.DataFrame:
    rows = []
    player_id = 1

    # --- Joueurs stars ---
    star_key = set()
    for name, pos_num, team_name, nat, boost in STAR_PLAYERS:
        team_code = next((tc for tn, tc in TEAMS if tn.replace("-", "").replace(" ", "").lower()
                          in team_name.replace("-", "").replace(" ", "").lower()), "XXX")
        pg = POSITION_MAP[pos_num][1]
        stats = gen_stats(pg, boost=boost)
        phys = gen_physical(pg)
        matches = int(np.clip(np.random.normal(18, 4), 8, 26))
        row = {
            "player_id": player_id,
            "name": name,
            "position_number": pos_num,
            "position_name": POSITION_MAP[pos_num][0],
            "position_raw": POSITION_MAP[pos_num][0],
            "position_group": pg,
            "position_source": "generated",
            "team": team_name,
            "team_code": team_code,
            "nationality": nat,
            "age": int(np.clip(np.random.normal(27, 3), 20, 36)),
            "matches_played": matches,
            "minutes_avg": round(float(np.clip(np.random.normal(68, 8), 40, 80)), 1),
            **phys,
            **stats,
        }
        rows.append(row)
        star_key.add((name, team_name))
        player_id += 1

    # --- Joueurs générés (2 à 3 par poste par équipe) ---
    for team_name, team_code in TEAMS:
        for pos_num, (pos_name, pg) in POSITION_MAP.items():
            n_players = 2 if pos_num in [2, 9, 10, 15] else 2
            for _ in range(n_players):
                nat = str(np.random.choice(NAT_NAMES, p=NAT_PROBS))
                name = gen_name(nat)
                # Éviter doublons exacts avec stars
                if (name, team_name) in star_key:
                    name = name + " Jr."

                stats = gen_stats(pg, boost=0.0)
                phys = gen_physical(pg)
                matches = int(np.clip(np.random.normal(16, 5), 5, 26))
                row = {
                    "player_id": player_id,
                    "name": name,
                    "position_number": pos_num,
                    "position_name": pos_name,
                    "position_raw": pos_name,
                    "position_group": pg,
                    "position_source": "generated",
                    "team": team_name,
                    "team_code": team_code,
                    "nationality": nat,
                    "age": int(np.clip(np.random.normal(26, 4), 19, 36)),
                    "matches_played": matches,
                    "minutes_avg": round(float(np.clip(np.random.normal(62, 12), 20, 80)), 1),
                    **phys,
                    **stats,
                }
                rows.append(row)
                player_id += 1

    return pd.DataFrame(rows)


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__))
    os.makedirs(out_dir, exist_ok=True)

    print("Génération des données joueurs...")
    df = generate_players()
    out_path = os.path.join(out_dir, "players.csv")
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"  {len(df)} joueurs generes -> {out_path}")
    print(f"  Équipes : {df['team'].nunique()}")
    print(f"  Groupes de poste : {sorted(df['position_group'].unique())}")
    print("\nAperçu :")
    print(df[["name", "position_group", "team", "rating"]].head(10) if "rating" in df.columns
          else df[["name", "position_group", "team"]].head(10))
