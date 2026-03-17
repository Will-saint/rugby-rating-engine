"""
Pipeline complet Rugby Rating Engine — collecte + traitement + export.

Architecture des sources :
  1. LNR (top14.lnr.fr) : roster, stats de base, profils physiques
  2. Statbunker : carries/meters/passes/tackles détaillés (complément)
  3. normalize.py : déduplication, calcul /80, validation, export CSV

Commandes :
    python run_pipeline.py --season 2023-2024            # pipeline complet
    python run_pipeline.py --season 2023-2024 --fast     # sans profils ni matches
    python run_pipeline.py --skip-scraping               # normalisation seule
    python run_pipeline.py --demo                        # données synthétiques
    python run_pipeline.py --dry-run                     # validation sans écriture
    python run_pipeline.py --clear-cache                 # vider le cache HTTP
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 en sortie console (Windows cp1252 sinon) — recommandation 11
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SCRAPERS_DIR = DATA_DIR / "scrapers"

# Seuils de régression (alertes si le dataset est trop petit)
REGRESSION_THRESHOLDS = {
    "min_players": 150,         # Minimum joueurs total
    "min_teams": 10,            # Minimum équipes
    "min_positions": 8,         # Minimum groupes de poste
    "min_stat_coverage": 0.20,  # Couverture stats minimale (20% sans Statbunker, 35% avec)
    "max_unknown_pos": 0.10,    # Maximum 10% de positions UNKNOWN
}

# Seuil couverture avec Statbunker
STAT_COVERAGE_WITH_STATBUNKER = 0.35


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[OK]", "WARN": "[!!]", "ERROR": "[XX]", "STEP": "\n==="}
    print(f"{ts} {icons.get(level, '[?]')} {msg}")


def log_step(title: str):
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


# ---------------------------------------------------------------------------
# Exécution de sous-scripts
# ---------------------------------------------------------------------------

def run_script(script: Path, args: list[str], timeout: int = 600) -> bool:
    cmd = [sys.executable, str(script)] + [str(a) for a in args]
    log(f"Lancement : {script.name} {' '.join(str(a) for a in args)}")
    try:
        result = subprocess.run(cmd, timeout=timeout)
        if result.returncode != 0:
            log(f"Échec (code {result.returncode})", "ERROR")
            return False
        return True
    except subprocess.TimeoutExpired:
        log(f"Timeout après {timeout}s", "ERROR")
        return False
    except Exception as e:
        log(f"Erreur : {e}", "ERROR")
        return False


# ---------------------------------------------------------------------------
# coverage_core — métriques réellement utilisées par weights.yaml (P1-7)
# ---------------------------------------------------------------------------

def get_core_stat_cols() -> list[str]:
    """
    Extrait l'ensemble des métriques utilisées dans weights.yaml.
    coverage_core = couverture sur ces colonnes uniquement (ce que le moteur utilise).
    """
    weights_path = ROOT / "config" / "weights.yaml"
    if not weights_path.exists():
        return []
    try:
        import yaml
        with open(weights_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        metrics = set()
        for pos_cfg in cfg.values():
            if isinstance(pos_cfg, dict):
                metrics.update(pos_cfg.keys())
        return sorted(metrics)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Tests de régression
# ---------------------------------------------------------------------------

def regression_check(csv_path: Path, season: str) -> dict:
    """
    Vérifie que le dataset respecte les seuils minimaux.
    Retourne un dict de résultats {test_name: passed}.
    """
    if not csv_path.exists():
        log(f"players.csv introuvable : {csv_path}", "ERROR")
        return {"file_exists": False}

    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
        n = len(df)

        # coverage_core = métriques utilisées par weights.yaml (ce que le moteur évalue)
        core_cols = get_core_stat_cols()
        available_core = [c for c in core_cols if c in df.columns]
        coverage = df[available_core].notna().mean().mean() if available_core else 0

        unknown_pos = (df.get("position_group", pd.Series()) == "UNKNOWN").mean()

        # Anomalies HIGH depuis validation_anomalies.json
        n_high = 0
        anom_path = DATA_DIR / "validation_anomalies.json"
        if anom_path.exists():
            try:
                with open(anom_path, encoding="utf-8") as f:
                    anoms = json.load(f)
                n_high = sum(1 for a in anoms if a.get("severity") == "HIGH")
            except Exception:
                pass

        results = {
            "file_exists": True,
            "min_players": n >= REGRESSION_THRESHOLDS["min_players"],
            "min_teams": df["team"].nunique() >= REGRESSION_THRESHOLDS["min_teams"],
            "min_positions": df["position_group"].nunique() >= REGRESSION_THRESHOLDS["min_positions"],
            "stat_coverage": coverage >= REGRESSION_THRESHOLDS["min_stat_coverage"],
            "unknown_positions": unknown_pos <= REGRESSION_THRESHOLDS["max_unknown_pos"],
            "no_high_anomalies": n_high == 0,
        }

        log_step(f"RÉGRESSION — Saison {season}")
        print(f"  Joueurs      : {n} (min={REGRESSION_THRESHOLDS['min_players']})")
        print(f"  Équipes      : {df['team'].nunique()}")
        print(f"  Postes       : {df['position_group'].nunique()}")
        print(f"  Couv. core   : {coverage:.0%} (min={REGRESSION_THRESHOLDS['min_stat_coverage']:.0%}, {len(available_core)}/{len(core_cols)} métriques)")
        print(f"  UNKNOWN pos  : {unknown_pos:.0%} (max={REGRESSION_THRESHOLDS['max_unknown_pos']:.0%})")
        print(f"  Anomalies HIGH : {n_high} (max=0)")
        print()
        for test, passed in results.items():
            if test == "file_exists":
                continue
            icon = "PASS" if passed else "FAIL"
            print(f"  [{icon:4s}] {test}")

        return results

    except Exception as e:
        log(f"Erreur régression : {e}", "ERROR")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Rapport de qualité
# ---------------------------------------------------------------------------

def quality_report(season: str):
    """Rapport de qualité affiché dans le terminal."""
    csv_path = DATA_DIR / "players.csv"
    if not csv_path.exists():
        return

    try:
        import pandas as pd
        import hashlib

        df = pd.read_csv(csv_path)
        file_hash = hashlib.md5(csv_path.read_bytes()).hexdigest()[:8]
        file_date = datetime.fromtimestamp(csv_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

        # coverage_core = colonnes de weights.yaml, coverage_extended = tout
        core_cols = get_core_stat_cols()
        all_stat_cols = [
            "tackles_per80", "tackle_success_pct", "carries_per80", "meters_per80",
            "passes_per80", "kick_meters_per80", "penalties_per80",
            "offloads_per80", "line_breaks_per80", "turnovers_won_per80",
            "turnovers_lost_per80", "points_scored_per80", "errors_per80",
            "ruck_arrivals_per80", "lineout_wins_per80", "scrum_success_pct",
        ]
        avail_core = [c for c in core_cols if c in df.columns]
        avail_ext = [c for c in all_stat_cols if c in df.columns]
        cov_core = df[avail_core].notna().mean().mean() * 100 if avail_core else 0
        cov_ext = df[avail_ext].notna().mean().mean() * 100 if avail_ext else 0

        print("\n" + "=" * 55)
        print(f"  RAPPORT QUALITÉ — {season}")
        print("=" * 55)
        print(f"  Fichier      : players.csv (hash={file_hash}, {file_date})")
        print(f"  Joueurs      : {len(df)}")
        print(f"  Équipes      : {df['team'].nunique()}")
        print(f"  Couv. core   : {cov_core:.0f}%  ({len(avail_core)}/{len(core_cols)} métriques moteur)")
        print(f"  Couv. étendue: {cov_ext:.0f}%  ({len(avail_ext)}/{len(all_stat_cols)} métriques total)")
        print()

        print("  Répartition par poste :")
        if "position_group" in df.columns:
            for pos, cnt in df["position_group"].value_counts().items():
                print(f"    {pos:14s} : {cnt}")

        print()
        print("  Équipes (nb joueurs) :")
        if "team" in df.columns:
            for team, cnt in df["team"].value_counts().head(14).items():
                print(f"    {team:25s} : {cnt}")

        # Sources
        if "_source" in df.columns:
            print()
            print("  Provenance :")
            for src, cnt in df["_source"].value_counts().items():
                print(f"    {src:25s} : {cnt}")

        print("=" * 55)

    except Exception as e:
        log(f"Erreur rapport : {e}", "WARN")


# ---------------------------------------------------------------------------
# Métadonnées de run (recommandation 8)
# ---------------------------------------------------------------------------

def generate_pipeline_metadata(
    season: str,
    steps: list[tuple[str, bool]],
    elapsed: float,
    has_statbunker: bool = False,
) -> dict:
    """
    Génère le fichier pipeline_run_metadata.json avec toutes les infos de traçabilité.
    """
    import hashlib

    source_mode = "LNR_SB_MIXED" if has_statbunker else "LNR_ONLY"
    meta = {
        "generated_at": datetime.now().isoformat(),
        "season": season,
        "duration_seconds": round(elapsed, 1),
        "steps": [{"name": n, "status": "OK" if ok else "FAIL"} for n, ok in steps],
        "source_mode": source_mode,
        "sources_used": [],
        "files": {},
        "quality": {},
    }

    # Sources utilisées
    if any(n == "LNR" for n, ok in steps if ok):
        meta["sources_used"].append("LNR")
    if has_statbunker and any(n == "Statbunker" for n, ok in steps if ok):
        meta["sources_used"].append("Statbunker")

    # Hashes des fichiers clés (inclut weights.yaml pour traçabilité moteur — P1-8)
    files_to_hash = {
        "players.csv": DATA_DIR / "players.csv",
        "players_scored.csv": DATA_DIR / "players_scored.csv",
        "lnr_raw.json": RAW_DIR / "lnr_raw.json",
        "statbunker_raw.json": RAW_DIR / "statbunker_raw.json",
        "players_merged.json": RAW_DIR / "players_merged.json",
        "weights.yaml": ROOT / "config" / "weights.yaml",
    }
    for name, path in files_to_hash.items():
        if path.exists():
            h = hashlib.md5(path.read_bytes()).hexdigest()[:12]
            size_kb = path.stat().st_size // 1024
            mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
            meta["files"][name] = {"md5": h, "size_kb": size_kb, "modified": mtime}

    # Qualité dataset
    csv_path = DATA_DIR / "players.csv"
    if csv_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(csv_path)
            core_cols = get_core_stat_cols()
            all_stat_cols = [
                "tackles_per80", "tackle_success_pct", "carries_per80", "meters_per80",
                "passes_per80", "kick_meters_per80", "penalties_per80",
                "offloads_per80", "line_breaks_per80", "turnovers_won_per80",
                "turnovers_lost_per80", "points_scored_per80", "errors_per80",
                "ruck_arrivals_per80", "lineout_wins_per80", "scrum_success_pct",
            ]
            avail_core = [c for c in core_cols if c in df.columns]
            avail_ext = [c for c in all_stat_cols if c in df.columns]
            cov_core = df[avail_core].notna().mean().mean() if avail_core else 0
            cov_ext = df[avail_ext].notna().mean().mean() if avail_ext else 0
            # Anomalies HIGH
            n_high = 0
            anom_path = DATA_DIR / "validation_anomalies.json"
            if anom_path.exists():
                try:
                    with open(anom_path, encoding="utf-8") as f:
                        anoms = json.load(f)
                    n_high = sum(1 for a in anoms if a.get("severity") == "HIGH")
                except Exception:
                    pass
            meta["quality"] = {
                "n_players": len(df),
                "n_teams": int(df["team"].nunique()),
                "n_positions": int(df["position_group"].nunique()),
                "core_cols_total": len(core_cols),
                "core_cols_found": len(avail_core),
                "coverage_core": round(cov_core, 3),
                "coverage_core_pct": round(cov_core * 100, 1),
                "coverage_extended_pct": round(cov_ext * 100, 1),
                "coverage_target_pct": round(
                    (STAT_COVERAGE_WITH_STATBUNKER if has_statbunker else 0.20) * 100, 1
                ),
                "unknown_pos_pct": round((df["position_group"] == "UNKNOWN").mean() * 100, 1),
                "high_anomalies": n_high,
            }
        except Exception as e:
            meta["quality"] = {"error": str(e)}

    # Métadonnées scraping LNR si disponibles
    lnr_meta_path = RAW_DIR / "lnr_scrape_meta.json"
    if lnr_meta_path.exists():
        try:
            with open(lnr_meta_path, encoding="utf-8") as f:
                lnr_scrape = json.load(f)
            meta["lnr_scrape"] = lnr_scrape
            # La saison réelle des données prime sur l'argument CLI
            if lnr_scrape.get("season") and lnr_scrape["season"] != season:
                meta["season"] = lnr_scrape["season"]
        except Exception:
            pass

    # Sauvegarder
    out_path = DATA_DIR / "pipeline_run_metadata.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log(f"Metadata -> {out_path.name}")
    return meta


# ---------------------------------------------------------------------------
# Étapes du pipeline
# ---------------------------------------------------------------------------

def step_lnr(season: str, fast: bool = False, with_matches: bool = False) -> bool:
    log_step("ÉTAPE 1 — LNR (source officielle)")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    script_args = [
        "--season", season,
        "--output", str(RAW_DIR / "lnr_raw.json"),
    ]
    if fast:
        script_args.append("--no-profiles")
    if with_matches:
        script_args += ["--with-matches", "--matches-output", str(RAW_DIR / "lnr_matches.json")]

    ok = run_script(SCRAPERS_DIR / "scraper_lnr.py", script_args, timeout=1800)

    lnr_path = RAW_DIR / "lnr_raw.json"
    if lnr_path.exists():
        size = lnr_path.stat().st_size
        try:
            with open(lnr_path, encoding="utf-8") as f:
                data = json.load(f)
            log(f"LNR : {len(data)} joueurs ({size // 1024} KB)")
        except Exception:
            log(f"LNR : {size // 1024} KB (JSON non parsable)", "WARN")
    else:
        log("lnr_raw.json ABSENT", "ERROR")

    return ok


def step_match_stats(season: str) -> bool:
    """
    Étape optionnelle : scrape les stats par match (feuilles-de-match/statistiques-du-match).
    Produit lnr_match_history.json (182 matches × ~44 joueurs pour 2025-2026).
    Utilisé pour le rolling form et la validation croisée.
    """
    log_step("ÉTAPE OPT — Stats par match (feuilles de match)")

    ok = run_script(
        SCRAPERS_DIR / "scraper_match_stats.py",
        ["--season", season, "--output", str(RAW_DIR / "lnr_match_history.json")],
        timeout=600,
    )

    mh_path = RAW_DIR / "lnr_match_history.json"
    if mh_path.exists():
        try:
            with open(mh_path, encoding="utf-8") as f:
                data = json.load(f)
            n_records = sum(len(m.get("players", [])) for m in data)
            log(f"Match history : {len(data)} matchs, {n_records} entrées joueur-match")
        except Exception:
            pass
    return ok


def step_statbunker(season: str, merge: bool = True) -> bool:
    log_step("ÉTAPE 2 — Statbunker (complément stats)")

    lnr_path = RAW_DIR / "lnr_raw.json"
    script_args = [
        "--season", season,
        "--output", str(RAW_DIR / "statbunker_raw.json"),
        "--anomalies-output", str(RAW_DIR / "cross_validation.json"),
    ]
    if lnr_path.exists() and merge:
        script_args += [
            "--lnr", str(lnr_path),
            "--merge",
            "--merged-output", str(RAW_DIR / "players_merged.json"),
        ]

    ok = run_script(SCRAPERS_DIR / "scraper_statbunker.py", script_args, timeout=900)

    sb_path = RAW_DIR / "statbunker_raw.json"
    if sb_path.exists():
        try:
            with open(sb_path, encoding="utf-8") as f:
                data = json.load(f)
            log(f"Statbunker : {len(data)} joueurs")
        except Exception:
            pass

    return ok


def step_normalize(dry_run: bool = False, season: str = "") -> bool:
    log_step("ÉTAPE 3 — Normalisation et export")

    # Choisir la meilleure source disponible
    merged = RAW_DIR / "players_merged.json"
    lnr = RAW_DIR / "lnr_raw.json"
    source = merged if merged.exists() else lnr

    if not source.exists():
        log("Aucun fichier source JSON trouvé", "ERROR")
        return False

    log(f"Source : {source.name}")

    script_args = [
        "--input", str(source),
        "--output", str(DATA_DIR / "players.csv"),
        "--aliases-dir", str(DATA_DIR),
    ]
    if dry_run:
        script_args.append("--dry-run")

    ok = run_script(SCRAPERS_DIR / "normalize.py", script_args, timeout=120)
    return ok


def step_compute_form() -> bool:
    """
    Étape optionnelle : calcule les métriques de forme rolling depuis lnr_match_history.json
    et merge dans players.csv (form_tackles_per80, form_line_breaks_per80, etc.).
    """
    log_step("ÉTAPE 3b — Calcul forme rolling (match history)")

    mh_path = RAW_DIR / "lnr_match_history.json"
    form_path = DATA_DIR / "player_form.csv"
    players_path = DATA_DIR / "players.csv"

    if not mh_path.exists():
        log("lnr_match_history.json absent — skip forme rolling", "WARN")
        return False

    ok = run_script(
        SCRAPERS_DIR / "compute_form.py",
        ["--input", str(mh_path), "--output", str(form_path), "--window", "5"],
        timeout=60,
    )
    if not ok or not form_path.exists():
        return False

    # Merge form data into players.csv
    if not players_path.exists():
        log("players.csv absent — merge forme impossible", "WARN")
        return ok

    try:
        import pandas as pd

        players = pd.read_csv(players_path)
        form = pd.read_csv(form_path)

        form_cols = [
            "matches_verified", "starter_rate", "form_window",
            "form_tackles_per80", "form_line_breaks_per80",
            "form_offloads_per80", "form_turnovers_per80",
        ]

        # Supprime anciennes colonnes de forme si présentes
        for col in form_cols:
            if col in players.columns:
                players.drop(columns=[col], inplace=True)

        players["_name_lower"] = players["name"].str.lower().str.strip()
        form["_name_lower"] = form["name"].str.lower().str.strip()

        merged = players.merge(
            form[["_name_lower"] + form_cols],
            on="_name_lower",
            how="left",
        )
        merged.drop(columns=["_name_lower"], inplace=True)
        merged.to_csv(players_path, index=False)

        matched = merged["form_tackles_per80"].notna().sum()
        log(f"Forme merge : {matched}/{len(players)} joueurs matchés ({matched/len(players):.1%})")
        return True

    except Exception as e:
        log(f"Erreur merge forme : {e}", "ERROR")
        return False


def step_score() -> bool:
    """
    Calcule les ratings (engine/ratings.py) sur players.csv et produit players_scored.csv.
    Recommandation 9 : ratings calculés dans le pipeline, pas au runtime Streamlit.
    players.csv = données brutes normalisées (sans rating)
    players_scored.csv = players.csv + colonnes rating, axis_*, confidence_score
    """
    log_step("ÉTAPE 4 — Calcul des ratings")
    csv_path = DATA_DIR / "players.csv"
    scored_path = DATA_DIR / "players_scored.csv"

    if not csv_path.exists():
        log("players.csv introuvable — skip calcul ratings", "WARN")
        return False

    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        import pandas as pd
        from engine.ratings import calculate_ratings, get_team_strength

        df = pd.read_csv(csv_path)
        df = calculate_ratings(df)
        df.to_csv(scored_path, index=False)

        ts = get_team_strength(df)
        ts.to_csv(DATA_DIR / "team_strength.csv", index=False)

        log(f"Scoring : {len(df)} joueurs, ratings {df['rating'].min():.1f}–{df['rating'].max():.1f} (moy {df['rating'].mean():.1f})")
        log(f"players_scored.csv -> {scored_path}")
        return True
    except Exception as e:
        log(f"Erreur calcul ratings : {e}", "ERROR")
        return False


def step_demo() -> bool:
    log_step("DEMO — Données synthétiques")
    script_args = ["--output", str(DATA_DIR / "players.csv")]
    ok = run_script(DATA_DIR / "generate_sample.py", script_args, timeout=60)
    if ok and (DATA_DIR / "players.csv").exists():
        try:
            import pandas as pd
            df = pd.read_csv(DATA_DIR / "players.csv")
            log(f"Demo : {len(df)} joueurs, {df['team'].nunique()} équipes")
        except Exception:
            pass
    return ok


def step_clear_cache():
    """Vide le cache HTTP disque."""
    cache_dir = RAW_DIR / "html_cache"
    if cache_dir.exists():
        files = list(cache_dir.glob("*.html"))
        for f in files:
            f.unlink()
        log(f"Cache vidé : {len(files)} fichiers supprimés")
    else:
        log("Aucun cache à vider")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Rugby Rating Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python run_pipeline.py --season 2023-2024          # Complet (LNR + Statbunker)
  python run_pipeline.py --season 2023-2024 --fast   # Rapide (sans profils joueurs)
  python run_pipeline.py --skip-scraping             # Normalisation seule
  python run_pipeline.py --demo                      # Données synthétiques
  python run_pipeline.py --clear-cache               # Vider cache HTTP
        """,
    )
    parser.add_argument("--season", default="2023-2024",
                        help="Saison (ex: 2023-2024, 2024-2025, 2025-2026)")
    parser.add_argument("--fast", action="store_true",
                        help="Mode rapide : sans profils individuels ni feuilles de match")
    parser.add_argument("--with-matches", action="store_true",
                        help="Scraper les stats par match (statistiques-du-match, ~3 min)")
    parser.add_argument("--skip-lnr", action="store_true",
                        help="Passer le scraping LNR (si déjà fait)")
    parser.add_argument("--skip-statbunker", action="store_true",
                        help="Passer Statbunker")
    parser.add_argument("--skip-scraping", action="store_true",
                        help="Normalisation seule (données déjà en raw/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validation sans écriture du CSV final")
    parser.add_argument("--demo", action="store_true",
                        help="Générer données synthétiques (mode démo)")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Vider le cache HTTP puis quitter")
    parser.add_argument("--no-regression", action="store_true",
                        help="Passer les tests de régression")
    args = parser.parse_args()

    start = time.time()

    if args.clear_cache:
        step_clear_cache()
        return

    log_step(f"PIPELINE RUGBY RATING ENGINE — {args.season}")
    steps = []
    has_statbunker = False

    if args.demo:
        ok = step_demo()
        steps.append(("Demo", ok))
    else:
        if not args.skip_scraping and not args.skip_lnr:
            ok = step_lnr(
                args.season,
                fast=args.fast,
                with_matches=args.with_matches,
            )
            steps.append(("LNR", ok))
            if not ok:
                log("LNR échoué — pipeline en mode dégradé", "WARN")

        if not args.skip_scraping and not args.skip_statbunker:
            ok = step_statbunker(args.season, merge=True)
            steps.append(("Statbunker", ok))
            has_statbunker = ok

        if not args.skip_scraping and args.with_matches:
            ok_mh = step_match_stats(args.season)
            steps.append(("MatchStats", ok_mh))

        ok = step_normalize(dry_run=args.dry_run, season=args.season)
        steps.append(("Normalisation", ok))

        if ok and not args.dry_run:
            # Merge forme rolling si lnr_match_history.json disponible
            ok_form = step_compute_form()
            if ok_form:
                steps.append(("Forme", ok_form))

            ok_score = step_score()
            steps.append(("Scoring", ok_score))

    # Rapport qualité
    if not args.dry_run:
        quality_report(args.season)

    # Tests de régression
    if not args.dry_run and not args.no_regression:
        reg = regression_check(DATA_DIR / "players.csv", args.season)
        failed_regs = [k for k, v in reg.items() if k != "file_exists" and not v]
        if failed_regs:
            log(f"RÉGRESSION : {len(failed_regs)} test(s) échoué(s) : {failed_regs}", "WARN")
            steps.append(("Régression", False))
        else:
            steps.append(("Régression", True))

    # Métadonnées pipeline (recommandation 8)
    elapsed = time.time() - start
    if not args.dry_run:
        generate_pipeline_metadata(
            season=args.season,
            steps=steps,
            elapsed=elapsed,
            has_statbunker=has_statbunker,
        )

    # Résumé final
    print(f"\n{'=' * 55}")
    print(f"  RÉSUMÉ  ({elapsed:.0f}s)")
    print(f"{'=' * 55}")
    for name, ok in steps:
        print(f"  [{'OK' if ok else 'FAIL':4s}] {name}")

    n_failed = sum(1 for _, ok in steps if not ok)
    if n_failed == 0:
        print("\n  Pipeline terminé avec succès !")
    else:
        print(f"\n  {n_failed} étape(s) en échec.")
        sys.exit(1)


if __name__ == "__main__":
    main()
