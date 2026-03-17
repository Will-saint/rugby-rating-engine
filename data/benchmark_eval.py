"""
Benchmark Eval — compare les ratings calcules aux tiers experts.

Charge data/benchmarks/top_players_reference.json + players_scored.csv.
Calcule :
  - % joueurs S-tier dans le Top 50 global
  - % joueurs S-tier dans le Top 5 de leur poste
  - % joueurs A-tier dans le Top 15 de leur poste
  - Score global de calibration [0-100]
  - Joueurs de reference non trouves dans le dataset

Supporte aussi reference_pool.json (format etendu avec expected_lnr / expected_sb_only).
Les joueurs expected_sb_only avec missing_reason sont traites comme "non-bugs".

Usage :
    python data/benchmark_eval.py
    python data/benchmark_eval.py --scored data/players_scored.csv
    python data/benchmark_eval.py --pool    # utilise reference_pool.json
    python data/benchmark_eval.py --json    # sortie JSON uniquement
    python data/benchmark_eval.py --output data/benchmark_eval_result.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def load_reference(ref_path: Path) -> dict:
    with open(ref_path, encoding="utf-8") as f:
        data = json.load(f)
    # Normaliser reference_pool.json → format standard {players: [...]}
    # reference_pool.json a expected_lnr + expected_sb_only au lieu de players
    if "expected_lnr" in data or "expected_sb_only" in data:
        lnr_players = data.get("expected_lnr", [])
        sb_players = data.get("expected_sb_only", [])
        # Marquer la source de chaque joueur
        for p in lnr_players:
            p.setdefault("pool", "expected_lnr")
        for p in sb_players:
            p.setdefault("pool", "expected_sb_only")
        data["players"] = lnr_players + sb_players
    return data


def find_player(df, name: str, team: str, position_group: str):
    """
    Trouve le joueur dans le dataframe.
    Strategies (par ordre de priorite) :
      1. Nom exact (case-insensitive)
      2. Correspondance partielle sur nom de famille + meme equipe
      3. Correspondance partielle sur nom de famille + meme poste
    """
    name_lower = name.lower()

    # 1. Exact match
    exact = df[df["name"].str.lower() == name_lower]
    if not exact.empty:
        return exact.iloc[0]

    # 2. Last name + team (gere les prenoms abreges type "A. Dupont")
    last_name = name.split()[-1].lower()
    team_lower = team.lower()
    by_lastname_team = df[
        df["name"].str.lower().str.contains(last_name, na=False)
        & df["team"].str.lower().str.contains(team_lower.split()[0], na=False)
    ]
    if not by_lastname_team.empty:
        # prefer same position
        same_pos = by_lastname_team[by_lastname_team["position_group"] == position_group]
        return same_pos.iloc[0] if not same_pos.empty else by_lastname_team.iloc[0]

    # 3. Last name + position only
    by_lastname_pos = df[
        df["name"].str.lower().str.contains(last_name, na=False)
        & (df["position_group"] == position_group)
    ]
    if not by_lastname_pos.empty:
        return by_lastname_pos.iloc[0]

    return None


def evaluate(df, ref: dict) -> dict:
    import pandas as pd
    import numpy as np

    players_ref = ref["players"]
    thresholds = ref.get("thresholds", {
        "S_top_global": 50, "S_top_position": 5,
        "A_top_global": 100, "A_top_position": 15,
        "B_top_position": 30,
    })

    # Index rapide pour accès aux métadonnées pool/missing_reason par nom
    ref_player_map = {p["name"]: p for p in players_ref}

    # Rank global (tous postes)
    df = df.copy()
    df["rank_global"] = df["rating"].rank(ascending=False, method="min").astype(int)

    results = []
    for ref_player in players_ref:
        name = ref_player["name"]
        team = ref_player["team"]
        pg = ref_player["position_group"]
        tier = ref_player["tier"]

        found = find_player(df, name, team, pg)

        if found is None:
            results.append({
                "name": name, "team": team, "position_group": pg, "tier": tier,
                "found": False,
                "rating": None, "rank_global": None, "rank_position": None,
                "in_top_global": False, "in_top_position": False,
                "pass": False,
            })
            continue

        rating = float(found["rating"])
        rank_global = int(found["rank_global"])
        rank_pos = int(found.get("rank_position", 999))
        matches_played = int(found.get("matches_played") or 0)
        confidence = float(found.get("confidence") or 0)

        # Joueur avec données insuffisantes : < 5 matchs Top14 ou conf < 0.25
        # Ces joueurs ne sont PAS pénalisés dans le score (cause externe : sélection/blessure).
        insufficient_data = matches_played < 5 or confidence < 0.25

        if tier == "S":
            top_g = thresholds["S_top_global"]
            top_p = thresholds["S_top_position"]
        elif tier == "A":
            top_g = thresholds["A_top_global"]
            top_p = thresholds["A_top_position"]
        else:
            top_g = 999
            top_p = thresholds["B_top_position"]

        in_top_g = rank_global <= top_g
        in_top_p = rank_pos <= top_p
        # Si données insuffisantes : on ne compte pas ce joueur dans le score
        passed = in_top_p if not insufficient_data else None

        results.append({
            "name": name,
            "matched_name": str(found.get("name", name)),
            "team": team,
            "position_group": pg,
            "tier": tier,
            "found": True,
            "insufficient_data": insufficient_data,
            "matches_played": matches_played,
            "confidence": round(confidence, 3),
            "rating": round(rating, 1),
            "rank_global": rank_global,
            "rank_position": rank_pos,
            "in_top_global": in_top_g,
            "in_top_position": in_top_p,
            "pass": passed,
        })

    # --- Metriques globales ---
    found_results = [r for r in results if r["found"]]
    not_found = [r for r in results if not r["found"]]

    n_total = len(players_ref)
    n_found = len(found_results)

    s_results = [r for r in found_results if r["tier"] == "S"]
    a_results = [r for r in found_results if r["tier"] == "A"]
    b_results = [r for r in found_results if r["tier"] == "B"]

    # pass=None pour les joueurs avec données insuffisantes (pas comptés)
    def pct_pass(lst):
        scorable = [r for r in lst if r["pass"] is not None]
        return round(sum(1 for r in scorable if r["pass"]) / len(scorable) * 100, 1) if scorable else 0.0
    def mean_rank(lst):
        valid = [r for r in lst if r.get("rank_position") is not None]
        return round(sum(r["rank_position"] for r in valid) / len(valid), 1) if valid else None

    # Score calibration : somme pondérée (S x3, A x2, B x1) — exclus les données insuffisantes
    calibration_score = 0.0
    calibration_weight = 0.0
    n_insufficient = sum(1 for r in found_results if r.get("insufficient_data"))
    for r in found_results:
        if r["pass"] is None:  # données insuffisantes
            continue
        w = {"S": 3, "A": 2, "B": 1}.get(r["tier"], 1)
        calibration_score += w * (1 if r["pass"] else 0)
        calibration_weight += w
    calibration_pct = round(calibration_score / calibration_weight * 100, 1) if calibration_weight > 0 else 0.0

    # Séparer les joueurs non trouvés : bugs (expected_lnr) vs attendus absents (sb_only + missing_reason)
    missing_lnr = []
    missing_sb = []
    for r in not_found:
        meta = ref_player_map.get(r["name"], {})
        has_reason = bool(meta.get("missing_reason"))
        is_sb_pool = meta.get("pool") == "expected_sb_only"
        if is_sb_pool or has_reason:
            missing_sb.append({
                "name": r["name"], "team": r["team"],
                "position_group": r["position_group"], "tier": r["tier"],
                "missing_reason": meta.get("missing_reason", "unknown"),
                "note": meta.get("note", ""),
            })
        else:
            missing_lnr.append({
                "name": r["name"], "team": r["team"],
                "position_group": r["position_group"], "tier": r["tier"],
            })

    return {
        "version": ref.get("version"),
        "n_reference": n_total,
        "n_found": n_found,
        "n_not_found": len(not_found),
        "pct_found": round(n_found / n_total * 100, 1) if n_total > 0 else 0.0,
        "calibration_score": calibration_pct,
        "n_insufficient_data": n_insufficient,
        "S_pct_in_top_position": pct_pass(s_results),
        "S_mean_rank_position": mean_rank(s_results),
        "A_pct_in_top_position": pct_pass(a_results),
        "A_mean_rank_position": mean_rank(a_results),
        "B_pct_in_top_position": pct_pass(b_results),
        "not_found_players": [f"{r['name']} ({r['team']}, {r['position_group']}, {r['tier']})" for r in not_found],
        "missing_expected_lnr": missing_lnr,
        "missing_expected_sb": missing_sb,
        "details": results,
    }


def print_report(eval_result: dict) -> None:
    e = eval_result
    sep = "=" * 65

    print(f"\n{sep}")
    print(f"  BENCHMARK EVAL — Saison {e.get('version', '?')}")
    print(sep)
    print(f"  Joueurs reference : {e['n_reference']}  |  Trouves : {e['n_found']} ({e['pct_found']}%)")
    n_ins = e.get("n_insufficient_data", 0)
    ins_note = f"  ({n_ins} exclus — données insuffisantes <5 matchs ou conf<0.25)" if n_ins else ""
    print(f"  Score calibration : {e['calibration_score']:.0f}/100  (S x3, A x2, B x1){ins_note}")
    print()
    print(f"  S-tier : {e['S_pct_in_top_position']:.0f}% dans leur Top-poste cible | rang moy = {e['S_mean_rank_position']}")
    print(f"  A-tier : {e['A_pct_in_top_position']:.0f}% dans leur Top-poste cible | rang moy = {e['A_mean_rank_position']}")
    print(f"  B-tier : {e['B_pct_in_top_position']:.0f}% dans leur Top-poste cible")
    print()

    if e.get("missing_expected_lnr"):
        print(f"  BUG — Attendus dans LNR mais introuvables ({len(e['missing_expected_lnr'])}) :")
        for p in e["missing_expected_lnr"]:
            print(f"    [BUG] {p['name']} ({p['team']}, {p['position_group']}, {p['tier']})")
        print()
    if e.get("missing_expected_sb"):
        print(f"  Info — Attendus SB-only ou blessés ({len(e['missing_expected_sb'])}) :")
        for p in e["missing_expected_sb"]:
            print(f"    [OK]  {p['name']} ({p['team']}) — {p.get('missing_reason', '?')}")
        print()
    elif e["not_found_players"] and not e.get("missing_expected_lnr") and not e.get("missing_expected_sb"):
        print(f"  Non trouves ({e['n_not_found']}) :")
        for p in e["not_found_players"]:
            print(f"    - {p}")
        print()

    print(f"  Detail par joueur :")
    print(f"  {'Tier':4s} {'Joueur':25s} {'Poste':12s} {'Rating':7s} {'Rg.Pos':7s} {'Top?':6s} {'Match'}")
    print(f"  {'-'*80}")
    for r in sorted(e["details"], key=lambda x: (x["tier"], not x["found"], x.get("rank_position") or 999)):
        if not r["found"]:
            print(f"  [{r['tier']:2s}]  {'NOT FOUND: ' + r['name']:25s} {r['position_group']:12s}  --       --      --")
            continue
        if r["pass"] is None:
            icon = "N/A "
            note = f"[DATA: {r.get('matches_played',0)} matchs, conf={r.get('confidence',0):.2f}]"
        else:
            icon = "PASS" if r["pass"] else "FAIL"
            note = "" if r["name"] == r.get("matched_name") else f"({r.get('matched_name', '')})"
        print(f"  [{r['tier']:2s}]  {r['name']:25s} {r['position_group']:12s}  {r['rating']:5.1f}    #{r['rank_position']:<5d}  {icon:4s}  {note}")
    print(sep)


def main():
    parser = argparse.ArgumentParser(description="Benchmark Eval — Rugby Rating Engine")
    parser.add_argument("--scored", type=str, default=None, help="Chemin vers players_scored.csv")
    parser.add_argument("--ref", type=str, default=None, help="Chemin vers le fichier reference JSON")
    parser.add_argument("--pool", action="store_true",
                        help="Utiliser reference_pool.json (format etendu LNR/SB) au lieu de top_players_reference.json")
    parser.add_argument("--json", action="store_true", help="Sortie JSON uniquement (machine-readable)")
    parser.add_argument("--output", type=str, default=None,
                        help="Ecrire le resultat JSON dans un fichier (defaut: data/benchmark_eval_result.json)")
    args = parser.parse_args()

    import pandas as pd

    scored_path = Path(args.scored) if args.scored else ROOT / "data" / "players_scored.csv"
    if args.ref:
        ref_path = Path(args.ref)
    elif args.pool:
        ref_path = ROOT / "data" / "benchmarks" / "reference_pool.json"
    else:
        ref_path = ROOT / "data" / "benchmarks" / "top_players_reference.json"

    if not scored_path.exists():
        print(f"[ERR] players_scored.csv introuvable : {scored_path}")
        sys.exit(1)
    if not ref_path.exists():
        print(f"[ERR] Reference JSON introuvable : {ref_path}")
        sys.exit(1)

    df = pd.read_csv(scored_path)
    ref = load_reference(ref_path)
    result = evaluate(df, ref)

    # Toujours sauvegarder dans benchmark_eval_result.json (sauf si --json seul)
    default_out = ROOT / "data" / "benchmark_eval_result.json"
    out_path = Path(args.output) if args.output else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if not args.json:
        print(f"[OK] Benchmark eval result -> {out_path}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
