"""
QA Check — 5 tests de régression automatiques (P3-20).

But : détecter les régressions silencieuses après un run de pipeline.

Tests :
  1. Saison confirmée (pipeline_run_metadata.json)
  2. Nombre d'équipes >= MIN_TEAMS
  3. Nombre de joueurs >= MIN_PLAYERS
  4. coverage_core >= MIN_COVERAGE_CORE
  5. Zéro anomalie HIGH

Usage :
    python qa_check.py                    # vérifie data/ courant
    python qa_check.py --season 2023-2024 # vérifie une saison spécifique
    python qa_check.py --strict           # fail si 1 test KO (exit code 1)
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

# Seuils — ajuster selon la saison
MIN_TEAMS = 10
MIN_PLAYERS = 150
MIN_COVERAGE_CORE = 0.20   # 20% sans Statbunker, 35% avec

# ============================================================
# Helpers
# ============================================================

def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_csv_stats(path: Path) -> dict | None:
    """Charge players.csv et calcule les métriques clés."""
    if not path.exists():
        return None
    try:
        import pandas as pd
        import yaml
        df = pd.read_csv(path)

        # Métriques core depuis weights.yaml
        weights_path = ROOT / "config" / "weights.yaml"
        core_cols = []
        if weights_path.exists():
            with open(weights_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            metrics = set()
            for pos_cfg in cfg.values():
                if isinstance(pos_cfg, dict):
                    metrics.update(pos_cfg.keys())
            core_cols = sorted(metrics)

        avail_core = [c for c in core_cols if c in df.columns]
        cov_core = df[avail_core].notna().mean().mean() if avail_core else 0

        return {
            "n_players": len(df),
            "n_teams": df["team"].nunique() if "team" in df.columns else 0,
            "coverage_core": cov_core,
            "n_core_available": len(avail_core),
            "n_core_total": len(core_cols),
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Les 5 tests
# ============================================================

def test_season_confirmed(meta: dict | None) -> tuple[bool, str]:
    """Test 1 : la saison scrappée correspond à la saison demandée."""
    if meta is None:
        return False, "pipeline_run_metadata.json introuvable"
    lnr = meta.get("lnr_scrape", {})
    confirmed = lnr.get("season_confirmed", None)
    if confirmed is True:
        return True, f"saison {meta.get('season', '?')} confirmée"
    if confirmed is False:
        return False, f"MISMATCH saison (demandée={meta.get('season','?')}, servie=?)"
    return True, "season_confirmed absent (smoke test non exécuté — warning)"


def test_min_teams(stats: dict | None) -> tuple[bool, str]:
    """Test 2 : nombre d'équipes dans le dataset >= MIN_TEAMS."""
    if stats is None:
        return False, "players.csv introuvable"
    if "error" in stats:
        return False, f"erreur lecture: {stats['error']}"
    n = stats["n_teams"]
    ok = n >= MIN_TEAMS
    return ok, f"{n} équipes (min={MIN_TEAMS})"


def test_min_players(stats: dict | None) -> tuple[bool, str]:
    """Test 3 : nombre de joueurs >= MIN_PLAYERS."""
    if stats is None:
        return False, "players.csv introuvable"
    if "error" in stats:
        return False, f"erreur lecture: {stats['error']}"
    n = stats["n_players"]
    ok = n >= MIN_PLAYERS
    return ok, f"{n} joueurs (min={MIN_PLAYERS})"


def test_coverage_core(stats: dict | None) -> tuple[bool, str]:
    """Test 4 : coverage_core >= MIN_COVERAGE_CORE."""
    if stats is None:
        return False, "players.csv introuvable"
    if "error" in stats:
        return False, f"erreur lecture: {stats['error']}"
    cov = stats["coverage_core"]
    ok = cov >= MIN_COVERAGE_CORE
    n_avail = stats.get("n_core_available", "?")
    n_total = stats.get("n_core_total", "?")
    return ok, f"{cov:.0%} ({n_avail}/{n_total} métriques core, min={MIN_COVERAGE_CORE:.0%})"


def test_no_fine_positions_lnr_only(csv_path: Path, meta: dict | None) -> tuple[bool, str]:
    """Test 6 : si LNR-only → aucun joueur HOOKER/NUMBER_8 dans players.csv."""
    if not csv_path.exists():
        return False, "players.csv introuvable"
    # Déterminer si la source est LNR-only depuis le metadata
    has_sb = False
    if meta:
        has_sb = "Statbunker" in meta.get("sources_used", [])
    if not has_sb:
        # Vérifier aussi la colonne position_source dans le CSV
        try:
            import pandas as pd
            df = pd.read_csv(csv_path, usecols=lambda c: c in ("position_group", "position_source"))
            if "position_source" in df.columns and (df["position_source"] == "sb").any():
                has_sb = True
        except Exception:
            pass

    if has_sb:
        return True, "source Statbunker presente — postes fins autorises (test non applicable)"

    # LNR-only : aucun HOOKER/NUMBER_8
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, usecols=["position_group"])
        fine_only = {"HOOKER", "NUMBER_8", "PROP", "FLANKER"}
        present = [p for p in fine_only if (df["position_group"] == p).any()]
        if present:
            counts = {p: int((df["position_group"] == p).sum()) for p in present}
            return False, f"LNR-only mais postes fins detectes : {counts}"
        return True, "LNR-only : aucun HOOKER/NUMBER_8/PROP/FLANKER (correct)"
    except Exception as e:
        return False, f"erreur lecture: {e}"


def test_no_high_anomalies(anom_path: Path) -> tuple[bool, str]:
    """Test 5 : zéro anomalie HIGH dans validation_anomalies.json."""
    anoms = _load_json(anom_path)
    if anoms is None:
        return True, "validation_anomalies.json absent (pas d'anomalies enregistrées)"
    if not isinstance(anoms, list):
        return False, "format inattendu"
    high = [a for a in anoms if a.get("severity") == "HIGH"]
    ok = len(high) == 0
    if ok:
        return True, f"0 anomalie HIGH ({len(anoms)} total)"
    examples = [f"{a.get('name','?')} ({a.get('field','?')}={a.get('value','?')})" for a in high[:3]]
    return False, f"{len(high)} anomalies HIGH : {', '.join(examples)}"


# ============================================================
# Runner principal
# ============================================================

def run_qa(strict: bool = False) -> bool:
    csv_path = DATA_DIR / "players.csv"
    meta_path = DATA_DIR / "pipeline_run_metadata.json"
    anom_path = DATA_DIR / "validation_anomalies.json"

    meta = _load_json(meta_path)
    stats = _load_csv_stats(csv_path)

    tests = [
        ("Saison confirmée",       test_season_confirmed(meta)),
        ("Equipes >= " + str(MIN_TEAMS), test_min_teams(stats)),
        ("Joueurs >= " + str(MIN_PLAYERS), test_min_players(stats)),
        ("Coverage core >= " + f"{MIN_COVERAGE_CORE:.0%}", test_coverage_core(stats)),
        ("Zero anomalie HIGH",     test_no_high_anomalies(anom_path)),
        ("Postes fins absents si LNR-only", test_no_fine_positions_lnr_only(csv_path, meta)),
    ]

    print("\n" + "=" * 60)
    print("  QA CHECK — Rugby Rating Engine")
    if meta:
        print(f"  Saison : {meta.get('season', '?')}  |  Run : {meta.get('generated_at', '?')[:16]}")
    print("=" * 60)

    all_pass = True
    for name, (ok, detail) in tests:
        icon = "[PASS]" if ok else "[FAIL]"
        print(f"  {icon:6s} {name}")
        print(f"         {detail}")
        if not ok:
            all_pass = False

    print("=" * 60)
    if all_pass:
        print("  Résultat : TOUS LES TESTS PASSENT")
    else:
        n_fail = sum(1 for _, (ok, _) in tests if not ok)
        print(f"  Résultat : {n_fail} ECHEC(S)")
    print()

    if strict and not all_pass:
        sys.exit(1)

    return all_pass


def main():
    global MIN_TEAMS, MIN_PLAYERS, MIN_COVERAGE_CORE
    parser = argparse.ArgumentParser(description="QA Check — Rugby Rating Engine")
    parser.add_argument("--strict", action="store_true",
                        help="Exit code 1 si un test échoue")
    parser.add_argument("--min-teams", type=int, default=MIN_TEAMS)
    parser.add_argument("--min-players", type=int, default=MIN_PLAYERS)
    parser.add_argument("--min-coverage", type=float, default=MIN_COVERAGE_CORE)
    args = parser.parse_args()

    MIN_TEAMS = args.min_teams
    MIN_PLAYERS = args.min_players
    MIN_COVERAGE_CORE = args.min_coverage

    run_qa(strict=args.strict)


if __name__ == "__main__":
    main()
