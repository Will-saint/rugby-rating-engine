"""
Scrape toutes les saisons post-COVID depuis LNR et génère un players_scored.csv par saison.

Saisons cibles (post-COVID) :
  2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026

Pour chaque saison :
  1. scraper_lnr.py          -> data/seasons/{saison}/lnr_raw.json
  2. normalize.py            -> data/seasons/{saison}/players.csv
  3. merge form (si dispo)   -> merge player_form.csv
  4. step_score (ratings)    -> data/seasons/{saison}/players_scored.csv

Note : les profils individuels (--with-profiles) sont optionnels (--with-profiles).
       Sans profils : ~1 min/saison. Avec profils : ~15 min/saison.

Usage :
    python data/scrapers/scrape_all_seasons.py
    python data/scrapers/scrape_all_seasons.py --seasons 2022-2023 2023-2024
    python data/scrapers/scrape_all_seasons.py --with-profiles
    python data/scrapers/scrape_all_seasons.py --skip-existing
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

SCRAPERS_DIR = ROOT / "data" / "scrapers"
SEASONS_DIR  = ROOT / "data" / "seasons"

POST_COVID_SEASONS = [
    "2020-2021",
    "2021-2022",
    "2022-2023",
    "2023-2024",
    "2024-2025",
    "2025-2026",
]


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "[INFO]", "OK": "[OK]  ", "WARN": "[WARN]", "ERR": "[ERR] "}.get(level, "[INFO]")
    print(f"{prefix} {msg}", flush=True)


def run_python(script: Path, args: list[str], timeout: int = 600) -> bool:
    """Lance un script Python et retourne True si succès."""
    cmd = [sys.executable, str(script)] + args
    log(f"  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=timeout, cwd=str(ROOT))
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"Timeout ({timeout}s) : {script.name}", "WARN")
        return False
    except Exception as e:
        log(f"Erreur : {e}", "ERR")
        return False


def process_season(season: str, with_profiles: bool = False, skip_existing: bool = False) -> bool:
    """
    Pipeline complet pour une saison :
    scrape -> normalize -> form (si dispo) -> score
    """
    season_dir = SEASONS_DIR / season
    season_dir.mkdir(parents=True, exist_ok=True)

    raw_path    = season_dir / "lnr_raw.json"
    players_csv = season_dir / "players.csv"
    scored_csv  = season_dir / "players_scored.csv"

    log(f"{'='*50}")
    log(f"SAISON {season}")
    log(f"{'='*50}")

    # ── Étape 1 : Scraping LNR ──────────────────────
    if skip_existing and raw_path.exists():
        log(f"lnr_raw.json existant — skip scraping ({raw_path})")
    else:
        log("Étape 1 — Scraping LNR (stats club)")
        scraper_args = [
            "--season", season,
            "--output", str(raw_path),
        ]
        if not with_profiles:
            scraper_args.append("--no-profiles")
        if not run_python(SCRAPERS_DIR / "scraper_lnr.py", scraper_args, timeout=900):
            log(f"Scraping LNR échoué pour {season}", "ERR")
            return False

    if not raw_path.exists():
        log(f"{raw_path} introuvable après scraping", "ERR")
        return False

    # ── Étape 2 : Normalisation ──────────────────────
    if skip_existing and players_csv.exists():
        log(f"players.csv existant — skip normalisation")
    else:
        log("Étape 2 — Normalisation")
        if not run_python(
            SCRAPERS_DIR / "normalize.py",
            ["--input", str(raw_path), "--output", str(players_csv), "--aliases-dir", str(ROOT / "data")],
            timeout=120,
        ):
            log(f"Normalisation échouée pour {season}", "ERR")
            return False

    if not players_csv.exists():
        log(f"{players_csv} introuvable après normalisation", "ERR")
        return False

    # ── Étape 3 : Scoring ───────────────────────────
    log("Étape 3 — Calcul ratings")
    try:
        import pandas as pd
        from engine.ratings import calculate_ratings, get_team_strength

        df = pd.read_csv(players_csv)
        df_scored = calculate_ratings(df)
        df_scored.to_csv(scored_csv, index=False)

        ts = get_team_strength(df_scored)
        ts.to_csv(season_dir / "team_strength.csv", index=False)

        n = len(df_scored)
        r_min = df_scored["rating"].min()
        r_max = df_scored["rating"].max()
        log(f"Scoring OK : {n} joueurs, ratings {r_min:.1f}–{r_max:.1f}", "OK")
    except Exception as e:
        log(f"Erreur scoring : {e}", "ERR")
        return False

    log(f"Saison {season} terminee -> {season_dir}", "OK")
    return True


def main():
    parser = argparse.ArgumentParser(description="Scrape toutes les saisons post-COVID")
    parser.add_argument(
        "--seasons", nargs="+", default=None,
        help="Saisons à traiter (défaut : toutes post-COVID)"
    )
    parser.add_argument(
        "--with-profiles", action="store_true",
        help="Inclure scraping profils individuels (taille, poids, âge) — lent"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Passer les étapes si les fichiers existent déjà"
    )
    args = parser.parse_args()

    seasons = args.seasons if args.seasons else POST_COVID_SEASONS

    log(f"Saisons a traiter : {seasons}")
    log(f"Profils individuels : {'oui' if args.with_profiles else 'non (--with-profiles pour activer)'}")

    results = {}
    total_start = time.time()

    for season in seasons:
        start = time.time()
        ok = process_season(
            season,
            with_profiles=args.with_profiles,
            skip_existing=args.skip_existing,
        )
        elapsed = time.time() - start
        results[season] = (ok, elapsed)
        if not ok:
            log(f"Saison {season} : ECHEC ({elapsed:.0f}s)", "WARN")
        else:
            log(f"Saison {season} : OK ({elapsed:.0f}s)", "OK")

    # Rapport final
    total_elapsed = time.time() - total_start
    log(f"\n{'='*50}")
    log(f"BILAN — {len(seasons)} saisons en {total_elapsed:.0f}s")
    for s, (ok, t) in results.items():
        status = "OK  " if ok else "FAIL"
        log(f"  {s} : {status} ({t:.0f}s)")
    log(f"{'='*50}")

    ok_count = sum(1 for ok, _ in results.values() if ok)
    log(f"Combine avec : python data/scrapers/combine_seasons.py")
    sys.exit(0 if ok_count == len(seasons) else 1)


if __name__ == "__main__":
    main()
