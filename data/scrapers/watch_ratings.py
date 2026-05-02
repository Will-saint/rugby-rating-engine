"""
data/scrapers/watch_ratings.py — Surveillance automatique des changements de note.

Compare players_scored.csv avec un snapshot précédent et signale les variations
significatives. Peut déclencher le pipeline en amont.

Usage :
    python watch_ratings.py                          # comparer seulement
    python watch_ratings.py --run-pipeline           # pipeline puis comparer
    python watch_ratings.py --auto                   # pipeline + comparer + snapshot
    python watch_ratings.py --threshold 5            # seuil personnalisé (défaut : 3.0)
    python watch_ratings.py --save-snapshot          # sauvegarder snapshot sans pipeline
    python watch_ratings.py --report-json            # sortie JSON en plus du terminal

Fichiers :
    data/players_scored.csv        → données courantes
    data/ratings_snapshot.csv      → référence du dernier run validé
    data/rating_changes.json       → rapport des changements détectés
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data"
SCRAPERS_DIR = DATA_DIR / "scrapers"

SNAPSHOT_PATH = DATA_DIR / "ratings_snapshot.csv"
CHANGES_PATH  = DATA_DIR / "rating_changes.json"
SCORED_PATH   = DATA_DIR / "players_scored.csv"

DEFAULT_THRESHOLD = 3.0
DEFAULT_SEASON    = "2025-2026"


# ─── Logging ────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[OK]", "WARN": "[!!]", "ERROR": "[XX]", "STEP": "==="}
    print(f"{ts} {icons.get(level, '[?]')} {msg}")


# ─── Pipeline ────────────────────────────────────────────────────────────────

def run_pipeline(season: str, fast: bool = False) -> bool:
    cmd = [
        sys.executable,
        str(SCRAPERS_DIR / "run_pipeline.py"),
        "--season", season,
        "--skip-scraping",      # scoring seul — scraping trop long pour l'auto
    ]
    if fast:
        cmd.append("--fast")
    log(f"Lancement pipeline (skip-scraping) — saison {season}")
    result = subprocess.run(cmd, timeout=300)
    return result.returncode == 0


# ─── Snapshot ───────────────────────────────────────────────────────────────

def save_snapshot(scored_path: Path = SCORED_PATH, snapshot_path: Path = SNAPSHOT_PATH):
    import shutil
    if not scored_path.exists():
        log(f"{scored_path.name} introuvable — snapshot non sauvegardé", "WARN")
        return False
    shutil.copy2(scored_path, snapshot_path)
    log(f"Snapshot sauvegardé → {snapshot_path.name}")
    return True


# ─── Comparaison ─────────────────────────────────────────────────────────────

def compare_ratings(
    current_path: Path,
    snapshot_path: Path,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[dict]:
    """
    Compare deux CSV de joueurs notés.
    Retourne la liste des joueurs dont |Δrating| >= threshold,
    triés par |Δrating| décroissant.
    """
    import pandas as pd

    if not current_path.exists():
        log(f"{current_path.name} introuvable", "ERROR")
        return []
    if not snapshot_path.exists():
        log("Pas de snapshot existant — aucune comparaison possible", "WARN")
        log("Lancez avec --save-snapshot pour créer le snapshot initial")
        return []

    cur = pd.read_csv(current_path)
    prev = pd.read_csv(snapshot_path)

    KEY = "lnr_slug" if "lnr_slug" in cur.columns and "lnr_slug" in prev.columns else "name"

    cur_r  = cur[[KEY, "name", "team", "position_group", "rating"]].rename(
        columns={"rating": "rating_new"})
    prev_r = prev[[KEY, "rating"]].rename(columns={"rating": "rating_prev"})

    merged = cur_r.merge(prev_r, on=KEY, how="outer")

    changes = []
    for _, row in merged.iterrows():
        r_new  = row.get("rating_new")
        r_prev = row.get("rating_prev")

        try:
            r_new  = float(r_new)  if r_new  is not None else None
            r_prev = float(r_prev) if r_prev is not None else None
        except (TypeError, ValueError):
            continue

        if r_new is None and r_prev is None:
            continue

        if r_prev is None:
            # Nouveau joueur
            delta = 0.0
            status = "NEW"
        elif r_new is None:
            # Joueur disparu
            delta = 0.0
            status = "REMOVED"
        else:
            delta = round(r_new - r_prev, 2)
            if abs(delta) < threshold:
                continue
            status = "UP" if delta > 0 else "DOWN"

        changes.append({
            "name":           str(row.get("name", "")),
            "team":           str(row.get("team", "")),
            "position_group": str(row.get("position_group", "")),
            "rating_prev":    r_prev,
            "rating_new":     r_new,
            "delta":          delta,
            "status":         status,
        })

    changes.sort(key=lambda x: abs(x["delta"] or 0), reverse=True)
    return changes


# ─── Rapport ─────────────────────────────────────────────────────────────────

def print_report(changes: list[dict], threshold: float):
    if not changes:
        log(f"Aucun changement significatif (seuil : ±{threshold:.1f} pts)")
        return

    up   = [c for c in changes if c["status"] == "UP"]
    down = [c for c in changes if c["status"] == "DOWN"]
    new_ = [c for c in changes if c["status"] == "NEW"]
    rem  = [c for c in changes if c["status"] == "REMOVED"]

    print(f"\n{'=' * 60}")
    print(f"  CHANGEMENTS DE NOTES (seuil ±{threshold:.1f}) — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'=' * 60}")
    print(f"  ↑ Progressions : {len(up)}   ↓ Régressions : {len(down)}"
          f"   + Nouveaux : {len(new_)}   - Retirés : {len(rem)}")
    print()

    for section, emoji, entries in [
        ("PROGRESSIONS", "↑", up),
        ("RÉGRESSIONS",  "↓", down),
    ]:
        if not entries:
            continue
        print(f"  {emoji} {section}")
        print(f"  {'Joueur':<28} {'Équipe':<20} {'Poste':<10} {'Avant':>6} {'Après':>6} {'Δ':>7}")
        print(f"  {'-'*28} {'-'*20} {'-'*10} {'-'*6} {'-'*6} {'-'*7}")
        for c in entries[:20]:   # afficher les 20 plus importants
            prev_s = f"{c['rating_prev']:.1f}" if c['rating_prev'] is not None else "—"
            new_s  = f"{c['rating_new']:.1f}"  if c['rating_new']  is not None else "—"
            delta_s = f"{c['delta']:+.1f}"
            print(f"  {c['name']:<28} {c['team']:<20} {c['position_group']:<10} "
                  f"{prev_s:>6} {new_s:>6} {delta_s:>7}")
        print()

    if new_:
        print(f"  + NOUVEAUX JOUEURS ({len(new_)})")
        for c in new_[:10]:
            print(f"    {c['name']:<28} {c['team']:<20} {c['position_group']}")
        print()

    if rem:
        print(f"  - RETIRÉS ({len(rem)})")
        for c in rem[:10]:
            print(f"    {c['name']:<28} note précédente : {c['rating_prev']:.1f}")
        print()

    print(f"  Total : {len(changes)} joueurs avec variation >= ±{threshold:.1f} pts")
    print(f"{'=' * 60}\n")


def save_changes_json(changes: list[dict], threshold: float):
    report = {
        "generated_at": datetime.now().isoformat(),
        "threshold":    threshold,
        "n_changes":    len(changes),
        "n_up":         sum(1 for c in changes if c["status"] == "UP"),
        "n_down":       sum(1 for c in changes if c["status"] == "DOWN"),
        "n_new":        sum(1 for c in changes if c["status"] == "NEW"),
        "n_removed":    sum(1 for c in changes if c["status"] == "REMOVED"),
        "changes":      changes,
    }
    with open(CHANGES_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"Rapport JSON → {CHANGES_PATH.name}  ({len(changes)} changements)")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Surveillance automatique des changements de note",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python watch_ratings.py                    # compare snapshot vs current
  python watch_ratings.py --run-pipeline     # pipeline (skip-scraping) puis compare
  python watch_ratings.py --auto             # pipeline + compare + update snapshot
  python watch_ratings.py --save-snapshot    # sauvegarder snapshot sans pipeline
  python watch_ratings.py --threshold 5      # seuil 5 pts (défaut 3)
  python watch_ratings.py --report-json      # sortie JSON rating_changes.json
        """,
    )
    parser.add_argument("--season", default=DEFAULT_SEASON,
                        help="Saison (ex: 2025-2026)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="Seuil minimal de variation de note pour alerte (défaut: 3.0)")
    parser.add_argument("--run-pipeline", action="store_true",
                        help="Lancer le pipeline (skip-scraping) avant la comparaison")
    parser.add_argument("--save-snapshot", action="store_true",
                        help="Sauvegarder le snapshot courant (sans pipeline ni comparaison)")
    parser.add_argument("--auto", action="store_true",
                        help="Pipeline + comparaison + mise à jour snapshot (mode cron)")
    parser.add_argument("--report-json", action="store_true",
                        help="Écrire rating_changes.json en plus du rapport terminal")
    parser.add_argument("--snapshot-path", type=Path, default=SNAPSHOT_PATH,
                        help="Chemin du snapshot de référence")
    args = parser.parse_args()

    # ── Mode snapshot seul ───────────────────────────────────────────────────
    if args.save_snapshot:
        save_snapshot(SCORED_PATH, args.snapshot_path)
        return

    # ── Mode auto : pipeline + compare + update ──────────────────────────────
    if args.auto:
        args.run_pipeline = True
        args.report_json  = True

    # ── Optionnel : lancer le pipeline ───────────────────────────────────────
    if args.run_pipeline:
        ok = run_pipeline(args.season)
        if not ok:
            log("Pipeline échoué — comparaison sur les données existantes", "WARN")

    # ── Comparaison ─────────────────────────────────────────────────────────
    changes = compare_ratings(SCORED_PATH, args.snapshot_path, threshold=args.threshold)
    print_report(changes, threshold=args.threshold)

    if args.report_json or args.auto:
        save_changes_json(changes, threshold=args.threshold)

    # ── Mode auto : mise à jour snapshot ────────────────────────────────────
    if args.auto:
        save_snapshot(SCORED_PATH, args.snapshot_path)

    # Exit code non-zero si changements détectés (utile en CI/cron)
    if changes:
        sys.exit(2)


if __name__ == "__main__":
    main()
