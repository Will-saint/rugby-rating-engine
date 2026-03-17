"""
Compute Form — calcule les métriques de forme récente depuis lnr_match_history.json.

Pour chaque joueur, calcule les N derniers matchs (défaut N=5) :
  form_tackles_per80    : plaquages/80 sur les N derniers matchs
  form_line_breaks_per80: franchissements/80 sur les N derniers matchs
  form_offloads_per80   : offloads/80 sur les N derniers matchs
  form_turnovers_per80  : ballons grattés/80 sur les N derniers matchs
  form_matches_played   : nombre de matchs joués dans la fenêtre

Également produit :
  starter_rate          : % matchs démarrés (>= 60 min jouées en moyenne)
  matches_verified      : nombre total de matchs depuis les feuilles de match

Usage :
    python data/scrapers/compute_form.py
    python data/scrapers/compute_form.py --window 3 --output data/player_form.csv
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"


def load_match_history(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_form(matches: list[dict], window: int = 5) -> list[dict]:
    """
    Pour chaque joueur, calcule les métriques de forme sur les N derniers matchs.
    """
    # Grouper les matchs par joueur (lnr_id)
    player_matches: dict[int, list[dict]] = defaultdict(list)

    for match in matches:
        date = match.get("date", "")
        round_slug = match.get("round", "")
        fixture_id = match.get("fixture_id")

        for p in match.get("players", []):
            lnr_id = p.get("lnr_id")
            if not lnr_id:
                continue
            player_matches[lnr_id].append({
                "date": date,
                "round": round_slug,
                "fixture_id": fixture_id,
                "name": p.get("name", ""),
                "team": p.get("team", ""),
                "minutes": p.get("minutes_played", 0),
                "tackles": p.get("tackles_success", 0),
                "line_breaks": p.get("line_breaks", 0),
                "offloads": p.get("offloads", 0),
                "turnovers": p.get("turnovers_won", 0),
                "points": p.get("points", 0),
            })

    results = []
    for lnr_id, pmatch_list in player_matches.items():
        # Trier par date (puis fixture_id si même date)
        sorted_matches = sorted(pmatch_list, key=lambda x: (x["date"], x.get("fixture_id", 0)))

        # Matches avec temps de jeu (> 0 min)
        played = [m for m in sorted_matches if m["minutes"] > 0]
        total_played = len(played)

        # Dernier nom/équipe
        last = sorted_matches[-1]
        name = last["name"]
        team = last["team"]

        # Starter rate: matchs avec ≥ 60 min
        starters = [m for m in played if m["minutes"] >= 60]
        starter_rate = len(starters) / total_played if total_played > 0 else 0.0

        # Fenêtre rolling (N derniers matchs avec temps de jeu)
        recent = played[-window:] if len(played) >= 1 else []
        n_recent = len(recent)

        if n_recent > 0:
            total_min = sum(m["minutes"] for m in recent)
            total_tackles = sum(m["tackles"] for m in recent)
            total_lb = sum(m["line_breaks"] for m in recent)
            total_off = sum(m["offloads"] for m in recent)
            total_to = sum(m["turnovers"] for m in recent)

            def per80(stat_total: float) -> float | None:
                if total_min <= 0:
                    return None
                return round(stat_total / total_min * 80, 2)

            form_tackles = per80(total_tackles)
            form_lb = per80(total_lb)
            form_off = per80(total_off)
            form_to = per80(total_to)
        else:
            form_tackles = form_lb = form_off = form_to = None
            n_recent = 0

        results.append({
            "lnr_id": lnr_id,
            "name": name,
            "team": team,
            "matches_verified": total_played,
            "starter_rate": round(starter_rate, 3),
            "form_window": n_recent,
            "form_tackles_per80": form_tackles,
            "form_line_breaks_per80": form_lb,
            "form_offloads_per80": form_off,
            "form_turnovers_per80": form_to,
        })

    return sorted(results, key=lambda x: x["name"])


def merge_with_players(form_df, players_csv: Path):
    """Merge form data with players.csv en utilisant lnr_id."""
    try:
        import pandas as pd
        players = pd.read_csv(players_csv)

        # lnr_id dans players.csv ?
        if "lnr_id" not in players.columns:
            print("[WARN] lnr_id absent de players.csv — merge impossible")
            return

        form_df["lnr_id"] = form_df["lnr_id"].astype(str)
        players["lnr_id"] = players["lnr_id"].astype(str)

        merged = players.merge(form_df, on="lnr_id", how="left", suffixes=("", "_form"))
        merged.to_csv(players_csv, index=False)
        matched = merged["form_tackles_per80"].notna().sum()
        print(f"[OK] Merge form : {matched}/{len(players)} joueurs matchés")
    except ImportError:
        print("[WARN] pandas non disponible")


def main():
    parser = argparse.ArgumentParser(description="Compute Player Form")
    parser.add_argument("--input", default=None,
                        help="lnr_match_history.json (défaut: data/raw/lnr_match_history.json)")
    parser.add_argument("--output", default=None,
                        help="CSV sortie (défaut: data/player_form.csv)")
    parser.add_argument("--window", type=int, default=5,
                        help="Fenêtre rolling en matches (défaut: 5)")
    parser.add_argument("--report", action="store_true",
                        help="Afficher rapport résumé")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else RAW_DIR / "lnr_match_history.json"
    output_path = Path(args.output) if args.output else DATA_DIR / "player_form.csv"

    if not input_path.exists():
        print(f"[ERR] {input_path} introuvable")
        print("      Lancer d'abord : python data/scrapers/scraper_match_stats.py --season 2025-2026")
        sys.exit(1)

    print(f"[INFO] Chargement {input_path}")
    matches = load_match_history(input_path)
    print(f"[INFO] {len(matches)} matchs chargés")

    form_data = compute_form(matches, window=args.window)

    try:
        import pandas as pd
        df = pd.DataFrame(form_data)
        df.to_csv(output_path, index=False)
        print(f"[OK] {len(df)} joueurs -> {output_path}")
    except ImportError:
        import csv
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if form_data:
                w = csv.DictWriter(f, fieldnames=list(form_data[0].keys()))
                w.writeheader()
                w.writerows(form_data)
        print(f"[OK] {len(form_data)} joueurs -> {output_path}")

    if args.report:
        import pandas as pd
        df = pd.read_csv(output_path)
        print(f"\nJoueurs trackés : {len(df)}")
        print(f"Médiane matchs vérifiés : {df['matches_verified'].median():.0f}")
        print(f"Taux de titulaire médian : {df['starter_rate'].median():.1%}")
        print(f"\nTop 10 form tackles/80 (fenêtre {args.window} matchs):")
        top = df.dropna(subset=["form_tackles_per80"]).nlargest(10, "form_tackles_per80")
        for _, r in top.iterrows():
            print(f"  {r['name']:25s} {r['team']:20s} {r['form_tackles_per80']:.1f} t/80")


if __name__ == "__main__":
    main()
