"""
Normalisation et validation du dataset final.

Etapes :
1. Charge players_merged.json (LNR + Rugbyrama)
2. Applique les aliases (players_aliases.csv, teams_aliases.csv)
3. Valide le schema (colonnes requises, valeurs plausibles)
4. Calcule les stats manquantes (per80 si totaux disponibles)
5. Filtre les joueurs avec trop peu de donnees
6. Exporte players.csv -> data/players.csv

Usage :
    python normalize.py --input ../raw/players_merged.json --output ../../data/players.csv
    python normalize.py --dry-run  # validation seule sans ecriture
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import numpy as np

# Force UTF-8 console (Windows cp1252) — recommandation 11
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Schemas et contraintes
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "player_id", "name", "team", "position_group",
    "matches_played", "minutes_avg",
]

# Uniquement les stats disponibles à 100% depuis LNR public (sans paywall).
# Les colonnes paywall (carries, meters, passes, kick_meters, penalties, errors,
# ruck_arrivals, lineout_wins, scrum_success_pct, tackle_success_pct,
# turnovers_lost) sont définitivement retirées du schéma.
OPTIONAL_STAT_COLUMNS = [
    "tackles_per80",
    "turnovers_won_per80",
    "line_breaks_per80",
    "offloads_per80",
    "points_scored_per80",
    "tries_per80",
]

# Colonnes paywall confirmées à 0% — exclues du CSV final
PAYWALL_COLUMNS = [
    "tackle_success_pct", "penalties_per80", "turnovers_lost_per80",
    "carries_per80", "meters_per80", "passes_per80", "kick_meters_per80",
    "errors_per80", "ruck_arrivals_per80", "lineout_wins_per80", "scrum_success_pct",
]

VALID_POSITIONS = {
    # Mode Groupes LNR : avants regroupés (LNR ne distingue pas Pilier/Talonneur
    # ni Flanker/N°8 dans ses statistiques par club)
    "FRONT_ROW", "LOCK", "BACK_ROW",
    # Backs : LNR est précis → positions fines conservées
    "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK",
}

# Plages de valeurs plausibles (min, max) pour sanity check
STAT_BOUNDS = {
    "tackles_per80":       (0, 30),
    "turnovers_won_per80": (0, 5),
    "line_breaks_per80":   (0, 8),
    "offloads_per80":      (0, 6),
    "points_scored_per80": (0, 30),
    "tries_per80":         (0, 5),
    "minutes_avg":         (0, 80),
    "matches_played":      (1, 26),
}

# Seuil minimum de donnees pour conserver un joueur
MIN_STAT_COVERAGE = 0.25  # au moins 25% des colonnes de stats renseignees


# ---------------------------------------------------------------------------
# Chargement des aliases
# ---------------------------------------------------------------------------

def load_aliases(aliases_dir: Path) -> tuple[dict, dict]:
    """
    Charge players_aliases.csv et teams_aliases.csv.
    Retourne (player_alias_dict, team_alias_dict).
    """
    player_aliases = {}
    team_aliases = {}

    player_path = aliases_dir / "players_aliases.csv"
    team_path = aliases_dir / "teams_aliases.csv"

    if player_path.exists():
        df = pd.read_csv(player_path)
        # Format attendu : alias, canonical_name
        for _, row in df.iterrows():
            player_aliases[str(row.get("alias", "")).strip().lower()] = str(
                row.get("canonical_name", "")
            ).strip()
        print(f"  [Aliases] {len(player_aliases)} aliases joueurs")
    else:
        print(f"  [Aliases] players_aliases.csv non trouve ({player_path}) — skipped")

    if team_path.exists():
        df = pd.read_csv(team_path)
        # Format attendu : alias, canonical_name
        for _, row in df.iterrows():
            team_aliases[str(row.get("alias", "")).strip()] = str(
                row.get("canonical_name", "")
            ).strip()
        print(f"  [Aliases] {len(team_aliases)} aliases equipes")
    else:
        print(f"  [Aliases] teams_aliases.csv non trouve ({team_path}) — skipped")

    return player_aliases, team_aliases


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def apply_aliases(df: pd.DataFrame, player_aliases: dict, team_aliases: dict) -> pd.DataFrame:
    """Remplace les noms variants par les noms canoniques."""
    if player_aliases:
        df["name"] = df["name"].apply(
            lambda n: player_aliases.get(str(n).strip().lower(), n)
        )
    if team_aliases:
        df["team"] = df["team"].apply(
            lambda t: team_aliases.get(str(t).strip(), t)
        )
    return df


def compute_missing_per80(df: pd.DataFrame) -> pd.DataFrame:
    """
    Si les totaux sont disponibles mais pas les /80 min, les calcule.
    minutes_total = matches_played * minutes_avg
    """
    if "minutes_total" not in df.columns:
        if "matches_played" in df.columns and "minutes_avg" in df.columns:
            df["minutes_total"] = df["matches_played"] * df["minutes_avg"]

    total_col = "minutes_total"
    if total_col not in df.columns:
        return df

    # Uniquement les paires dont le total LNR est effectivement scraped
    stat_pairs = [
        ("tackles_total",       "tackles_per80"),
        ("line_breaks_total",   "line_breaks_per80"),
        ("offloads_total",      "offloads_per80"),
        ("points_scored_total", "points_scored_per80"),
        ("tries_total",         "tries_per80"),
        ("turnovers_won_total", "turnovers_won_per80"),
    ]

    filled = 0
    for total_field, per80_field in stat_pairs:
        if total_field in df.columns and per80_field not in df.columns:
            mask = (df[total_field].notna()) & (df[total_col] > 0)
            df.loc[mask, per80_field] = (
                df.loc[mask, total_field] / df.loc[mask, total_col] * 80
            ).round(2)
            filled += mask.sum()

    # Fallback : tackles_success_total (plaquages réussis LNR) → tackles_per80
    # LNR ne publie pas le total des plaquages tentés, seulement les réussis.
    # On utilise tackles_success_total comme approximation de tackles_per80.
    if "tackles_success_total" in df.columns and "tackles_per80" in df.columns:
        mask = df["tackles_per80"].isna() & df["tackles_success_total"].notna() & (df[total_col] > 0)
        df.loc[mask, "tackles_per80"] = (
            df.loc[mask, "tackles_success_total"] / df.loc[mask, total_col] * 80
        ).round(2)
        filled += mask.sum()

    if filled > 0:
        print(f"  [Compute] {filled} valeurs /80 calculees depuis les totaux")
    return df


def validate_bounds(df: pd.DataFrame, verbose: bool = True) -> list[dict]:
    """
    Detecte les valeurs hors bornes plausibles.
    Retourne une liste d'anomalies.
    """
    anomalies = []
    for col, (lo, hi) in STAT_BOUNDS.items():
        if col not in df.columns:
            continue
        bad = df[(df[col].notna()) & ((df[col] < lo) | (df[col] > hi))]
        for _, row in bad.iterrows():
            anomalies.append({
                "name": row.get("name", "?"),
                "team": row.get("team", "?"),
                "field": col,
                "value": row[col],
                "expected": f"[{lo}, {hi}]",
                "severity": "HIGH" if abs(row[col]) > hi * 2 or row[col] < 0 else "MEDIUM",
            })

    if verbose and anomalies:
        high = sum(1 for a in anomalies if a["severity"] == "HIGH")
        print(f"  [Validate] {len(anomalies)} valeurs hors bornes ({high} HIGH)")

    return anomalies


def filter_low_coverage(df: pd.DataFrame, min_coverage: float = MIN_STAT_COVERAGE) -> pd.DataFrame:
    """Supprime les joueurs avec trop peu de stats renseignees."""
    available = [c for c in OPTIONAL_STAT_COLUMNS if c in df.columns]
    if not available:
        return df

    coverage = df[available].notna().mean(axis=1)
    mask = coverage >= min_coverage
    dropped = (~mask).sum()
    if dropped > 0:
        print(f"  [Filter] {dropped} joueurs supprimes (couverture stats < {min_coverage:.0%})")
    return df[mask].copy()


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Supprime les doublons (meme joueur avec plusieurs sources).
    Conserve la ligne avec le plus de stats renseignees.
    """
    available = [c for c in OPTIONAL_STAT_COLUMNS if c in df.columns]
    df["_coverage_count"] = df[available].notna().sum(axis=1)
    df = df.sort_values("_coverage_count", ascending=False)
    df = df.drop_duplicates(subset=["player_id"], keep="first")
    df = df.drop(columns=["_coverage_count"])
    return df


POSITION_LEGACY_REMAP = {
    # Anciens codes fins → groupes LNR-only (migration v1→v2)
    "PROP": "FRONT_ROW",
    "HOOKER": "FRONT_ROW",
    "FLANKER": "BACK_ROW",
    "NUMBER_8": "BACK_ROW",
}


def ensure_position_group(df: pd.DataFrame) -> pd.DataFrame:
    """Marque les positions invalides et les met en UNKNOWN.
    Migre aussi les anciens codes PROP/HOOKER/FLANKER/NUMBER_8 vers les groupes LNR.
    """
    if "position_group" not in df.columns:
        df["position_group"] = "UNKNOWN"
    # Migration legacy (données scrapées avant migration v2)
    legacy_mask = df["position_group"].isin(POSITION_LEGACY_REMAP)
    if legacy_mask.any():
        df.loc[legacy_mask, "position_group"] = df.loc[legacy_mask, "position_group"].map(
            POSITION_LEGACY_REMAP
        )
        print(f"  [Positions] {legacy_mask.sum()} joueurs migrants (PROP/HOOKER/FLANKER/N8 -> groupes LNR)")
    invalid = ~df["position_group"].isin(VALID_POSITIONS | {"UNKNOWN"})
    df.loc[invalid, "position_group"] = "UNKNOWN"
    unknown_after = (df["position_group"] == "UNKNOWN").sum()
    if unknown_after > 0:
        print(f"  [Positions] {unknown_after} joueurs en position UNKNOWN")
    return df


def add_default_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les colonnes manquantes avec des valeurs par defaut."""
    defaults = {
        "nationality": "",
        "age": None,
        "height_cm": None,
        "weight_kg": None,
        "team_code": "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # team_code depuis team si vide
    if "team_code" in df.columns and "team" in df.columns:
        mask = df["team_code"].isna() | (df["team_code"] == "")
        df.loc[mask, "team_code"] = df.loc[mask, "team"].str[:3].str.upper()

    return df


def clip_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Coupe les valeurs hors bornes plausibles (ne les supprime pas, les plafonne)."""
    for col, (lo, hi) in STAT_BOUNDS.items():
        if col in df.columns:
            df[col] = df[col].clip(lower=max(0, lo), upper=hi * 1.5)
    return df


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def normalize_pipeline(
    input_path: Path,
    output_path: Path,
    aliases_dir: Path,
    dry_run: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Pipeline complet de normalisation.
    Retourne (DataFrame final, liste des anomalies).
    """
    print(f"\n[Normalize] Chargement: {input_path}")

    # Charge
    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw)
    print(f"  -> {len(df)} joueurs charges")

    # Anti-joueurs fantômes : exiger player_id + lnr_url + team (recommandation 12)
    dropped_records = []
    drop_mask = pd.Series(False, index=df.index)

    if "player_id" in df.columns:
        no_id = df["player_id"].isna() | (df["player_id"].astype(str).str.strip() == "")
        if no_id.any():
            dropped_records.extend(
                df[no_id].assign(_drop_reason="no_player_id").to_dict("records")
            )
            drop_mask |= no_id
            print(f"  [AntiFantome] {no_id.sum()} joueurs sans player_id exclus")

    if "lnr_url" in df.columns:
        no_url = df["lnr_url"].isna() | (df["lnr_url"].astype(str).str.strip().isin(["", "nan"]))
        new_drops = no_url & ~drop_mask
        if new_drops.any():
            dropped_records.extend(
                df[new_drops].assign(_drop_reason="no_lnr_url").to_dict("records")
            )
            drop_mask |= no_url
            print(f"  [AntiFantome] {new_drops.sum()} joueurs sans lnr_url exclus")

    if "team" in df.columns:
        no_team = df["team"].isna() | (df["team"].astype(str).str.strip() == "")
        new_drops = no_team & ~drop_mask
        if new_drops.any():
            dropped_records.extend(
                df[new_drops].assign(_drop_reason="no_team").to_dict("records")
            )
            drop_mask |= no_team
            print(f"  [AntiFantome] {new_drops.sum()} joueurs sans equipe exclus")

    if drop_mask.any():
        df = df[~drop_mask].copy()

    # Sauvegarder dropped_players.json pour debug (recommandation 12)
    if dropped_records and not dry_run:
        dropped_path = output_path.parent / "dropped_players.json"
        with open(dropped_path, "w", encoding="utf-8") as f:
            json.dump(dropped_records, f, ensure_ascii=False, indent=2, default=str)
        print(f"  [AntiFantome] dropped_players.json -> {len(dropped_records)} lignes")

    # Aliases
    player_aliases, team_aliases = load_aliases(aliases_dir)
    df = apply_aliases(df, player_aliases, team_aliases)

    # Positions
    df = ensure_position_group(df)

    # Calcul des /80 manquants
    df = compute_missing_per80(df)

    # Defaults
    df = add_default_columns(df)

    # minutes_avg depuis minutes_total si absent
    if "minutes_avg" not in df.columns:
        if "minutes_total" in df.columns and "matches_played" in df.columns:
            mask = df["matches_played"] > 0
            df.loc[mask, "minutes_avg"] = (
                df.loc[mask, "minutes_total"] / df.loc[mask, "matches_played"]
            ).round(1)
        else:
            df["minutes_avg"] = 60.0  # default

    # Clip valeurs extremes
    df = clip_stats(df)

    # Deduplication
    before_dedup = len(df)
    df = deduplicate(df)
    if len(df) < before_dedup:
        print(f"  [Dedup] {before_dedup - len(df)} doublons supprimes")

    # Filtre couverture minimale
    df = filter_low_coverage(df)

    # Validation
    anomalies = validate_bounds(df, verbose=verbose)

    # Rapport final
    coverage_pct = df[[c for c in OPTIONAL_STAT_COLUMNS if c in df.columns]].notna().mean().mean()
    print(f"\n[Normalize] Resume:")
    print(f"  Joueurs : {len(df)}")
    print(f"  Equipes : {df['team'].nunique()}")
    print(f"  Postes  : {df['position_group'].value_counts().to_dict()}")
    print(f"  Couverture stats moy. : {coverage_pct:.1%}")
    print(f"  Anomalies : {len(anomalies)}")

    # Verifier les colonnes requises
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        print(f"\n  [WARN] Colonnes requises manquantes: {missing_cols}")

    if not dry_run:
        # Supprimer les colonnes paywall (0% de couverture LNR public)
        df = df.drop(columns=[c for c in PAYWALL_COLUMNS if c in df.columns], errors="ignore")

        # Selectionner et ordonner les colonnes de sortie
        out_cols = [
            "player_id", "lnr_id", "lnr_slug", "photo_url", "name", "team", "team_code", "position_group",
            "position_raw", "nationality", "age", "height_cm", "weight_kg",
            "season", "matches_played", "minutes_total", "minutes_avg",
            *[c for c in ["yellow_cards", "orange_cards", "red_cards"] if c in df.columns],
        ] + [c for c in OPTIONAL_STAT_COLUMNS if c in df.columns] + [
            c for c in ["_source"] if c in df.columns
        ]
        out_cols = [c for c in out_cols if c in df.columns]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        df[out_cols].to_csv(output_path, index=False, encoding="utf-8")
        print(f"\n[OK] Exporte -> {output_path}")

        # Sauvegarde des anomalies (toujours, même si vide, pour que QA puisse lire)
        anom_path = output_path.parent / "validation_anomalies.json"
        with open(anom_path, "w", encoding="utf-8") as f:
            json.dump(anomalies, f, ensure_ascii=False, indent=2)
        if anomalies:
            print(f"[OK] Anomalies -> {anom_path}")

    return df, anomalies


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Normalisation dataset rugby")
    parser.add_argument("--input", default="../raw/players_merged.json")
    parser.add_argument("--output", default="../../data/players.csv")
    parser.add_argument("--aliases-dir", default="../",
                        help="Dossier contenant players_aliases.csv et teams_aliases.csv")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validation uniquement sans ecriture")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    base = Path(__file__).parent
    input_path = (base / args.input).resolve()
    output_path = (base / args.output).resolve()
    aliases_dir = (base / args.aliases_dir).resolve()

    _, anomalies = normalize_pipeline(
        input_path=input_path,
        output_path=output_path,
        aliases_dir=aliases_dir,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    # Fail avec exit code 1 si anomalies HIGH detectees (P0-4)
    high_count = sum(1 for a in anomalies if a.get("severity") == "HIGH")
    if high_count > 0:
        print(f"\n[ERREUR] {high_count} anomalie(s) HIGH detectee(s) — pipeline KO")
        print("  Verifiez validation_anomalies.json et corrigez les donnees source.")
        sys.exit(1)


if __name__ == "__main__":
    main()
