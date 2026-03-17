"""
Audit des valeurs de position brutes dans le dataset LNR.

Lit lnr_raw.json (ou players.csv) et génère data/position_audit.json avec :
  - Liste des position_raw uniques et leurs comptages
  - Source de mapping utilisée (lnr_explicit | lnr_keyword | unknown)
  - Exemples de joueurs pour les valeurs rares ou non reconnues

Usage :
    python position_audit.py                       # lit data/lnr_raw.json
    python position_audit.py --csv data/players.csv
    python position_audit.py --verbose             # affiche le rapport dans la console
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data"
RAW_JSON = DATA_DIR / "lnr_raw.json"
OUTPUT_PATH = DATA_DIR / "position_audit.json"

# Import the mapper from the scraper
import sys
sys.path.insert(0, str(Path(__file__).parent))
from scraper_lnr import _position_group, POSITION_FR_TO_GROUP


def audit_from_json(raw_path: Path) -> list[dict]:
    """Charge lnr_raw.json et retourne une liste de dicts avec position_raw."""
    if not raw_path.exists():
        return []
    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)
    # lnr_raw.json peut être une liste de joueurs ou {team: [players]}
    players = []
    if isinstance(data, list):
        players = data
    elif isinstance(data, dict):
        for team_players in data.values():
            if isinstance(team_players, list):
                players.extend(team_players)
    return players


def audit_from_csv(csv_path: Path) -> list[dict]:
    """Charge players.csv pour l'audit position."""
    import pandas as pd
    df = pd.read_csv(csv_path)
    return df.to_dict("records")


def build_audit(players: list[dict]) -> dict:
    """
    Construit le rapport d'audit position.
    """
    raw_counts: Counter = Counter()
    group_for_raw: dict[str, str] = {}
    source_for_raw: dict[str, str] = {}
    examples_for_raw: dict[str, list] = defaultdict(list)

    for p in players:
        pos_raw = str(p.get("position_raw") or p.get("position", "")).strip()
        if not pos_raw:
            pos_raw = "<vide>"

        raw_counts[pos_raw] += 1

        if pos_raw not in group_for_raw:
            group, source = _position_group(pos_raw) if pos_raw != "<vide>" else ("UNKNOWN", "unknown")
            group_for_raw[pos_raw] = group
            source_for_raw[pos_raw] = source

        # Conserver jusqu'à 3 exemples par valeur rare/ambiguë
        if len(examples_for_raw[pos_raw]) < 3:
            examples_for_raw[pos_raw].append({
                "name": p.get("name", "?"),
                "team": p.get("team", "?"),
            })

    rows = []
    for pos_raw, count in raw_counts.most_common():
        group = group_for_raw[pos_raw]
        source = source_for_raw[pos_raw]
        rows.append({
            "position_raw": pos_raw,
            "count": count,
            "position_group": group,
            "position_source": source,
            "examples": examples_for_raw[pos_raw],
        })

    # Résumé
    n_explicit = sum(1 for r in rows if r["position_source"] == "lnr_explicit")
    n_keyword = sum(1 for r in rows if r["position_source"] == "lnr_keyword")
    n_unknown = sum(1 for r in rows if r["position_source"] == "unknown")
    n_players_total = sum(r["count"] for r in rows)
    n_players_explicit = sum(r["count"] for r in rows if r["position_source"] == "lnr_explicit")
    n_players_keyword = sum(r["count"] for r in rows if r["position_source"] == "lnr_keyword")
    n_players_unknown = sum(r["count"] for r in rows if r["position_source"] == "unknown")

    pct_explicit = round(n_players_explicit / n_players_total * 100, 1) if n_players_total else 0
    pct_keyword = round(n_players_keyword / n_players_total * 100, 1) if n_players_total else 0
    pct_unknown = round(n_players_unknown / n_players_total * 100, 1) if n_players_total else 0

    # Postes fins disponibles : seulement si source Statbunker (SB) est présente
    has_sb_source = any(r.get("position_source") == "sb" for r in rows)
    fine_positions_available = [
        g for g in set(r["position_group"] for r in rows)
        if g not in {"FRONT_ROW", "LOCK", "BACK_ROW", "UNKNOWN"}
    ]
    # Conclure sur la granularité disponible
    if has_sb_source:
        conclusion = (
            "Source mixte LNR+Statbunker -> postes fins POSSIBLES (HOOKER/NUMBER_8 si SB disponible). "
            f"Postes fins detectes : {sorted(fine_positions_available) or 'aucun'}."
        )
    else:
        conclusion = (
            "Source LNR-only -> postes fins IMPOSSIBLES. "
            "LNR ne differencie pas Pilier/Talonneur ni Flanker/N8 dans ses donnees. "
            "Postes en groupes : FRONT_ROW (1,2,3) / LOCK (4,5) / BACK_ROW (6,7,8). "
            "Integrer Statbunker pour obtenir HOOKER et NUMBER_8."
        )

    return {
        "summary": {
            "n_unique_position_raw": len(rows),
            "n_players_total": n_players_total,
            "n_explicit_mappings": n_explicit,
            "n_keyword_fallbacks": n_keyword,
            "n_unmapped": n_unknown,
            "n_players_unmapped": n_players_unknown,
            "pct_explicit": pct_explicit,
            "pct_keyword": pct_keyword,
            "pct_unknown": pct_unknown,
            "has_statbunker": has_sb_source,
            "conclusion": conclusion,
        },
        "by_position_raw": rows,
    }


def print_report(audit: dict) -> None:
    s = audit["summary"]
    print("\n" + "=" * 70)
    print("  POSITION AUDIT")
    print("=" * 70)
    print(f"  Joueurs total     : {s['n_players_total']}")
    print(f"  Valeurs uniques   : {s['n_unique_position_raw']}")
    print(f"  Explicit          : {s['n_explicit_mappings']} valeurs ({s['pct_explicit']}% joueurs)")
    print(f"  Keyword fallback  : {s['n_keyword_fallbacks']} valeurs ({s['pct_keyword']}% joueurs)")
    print(f"  Non reconnus      : {s['n_unmapped']} valeurs ({s['pct_unknown']}% joueurs) - {s['n_players_unmapped']} joueurs")
    print(f"  Source Statbunker : {'OUI' if s['has_statbunker'] else 'NON'}")
    print("-" * 70)
    print(f"  CONCLUSION : {s['conclusion']}")
    print("=" * 70)

    print("\n  Détail (toutes valeurs) :")
    for row in audit["by_position_raw"]:
        flag = "OK" if row["position_source"] == "lnr_explicit" else ("KW" if row["position_source"] == "lnr_keyword" else "XX")
        print(f"  [{flag}] {row['position_raw']!r:32s}  ->  {row['position_group']:12s}  ({row['count']:3d} joueurs)")
        if row["position_source"] in ("lnr_keyword", "unknown") and row["examples"]:
            for ex in row["examples"][:2]:
                print(f"           ex: {ex['name']} ({ex['team']})")
    print()


def main():
    parser = argparse.ArgumentParser(description="Audit positions brutes LNR")
    parser.add_argument("--csv", type=str, default=None, help="Lire depuis players.csv au lieu de lnr_raw.json")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH), help="Chemin de sortie JSON")
    parser.add_argument("--verbose", action="store_true", help="Affiche le rapport dans la console")
    args = parser.parse_args()

    if args.csv:
        players = audit_from_csv(Path(args.csv))
    else:
        players = audit_from_json(RAW_JSON)

    if not players:
        print(f"[WARN] Aucun joueur trouvé — vérifier {RAW_JSON} ou utiliser --csv")
        return

    audit = build_audit(players)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[OK] position_audit.json écrit → {out}")

    if args.verbose or True:  # toujours afficher le résumé
        print_report(audit)


if __name__ == "__main__":
    main()
