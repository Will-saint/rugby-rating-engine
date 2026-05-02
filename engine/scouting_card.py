"""
engine/scouting_card.py — Fiche scouting PDF/PNG (matplotlib, sans dépendances externes).

Génère une image haute résolution (A4 paysage) avec :
  ┌─────────────────────────────────────────────────────────┐
  │  HEADER : Nom · Poste · Équipe · Note · Tier · Drapeau │
  ├───────────────────┬─────────────────────────────────────┤
  │  Radar 6 axes     │  Sparkline forme + trend badge       │
  │  Club vs Intl     │  Métriques /80 comparées à poste     │
  ├───────────────────┴─────────────────────────────────────┤
  │  Stats table · Données intl · Watermark RugbyRating     │
  └─────────────────────────────────────────────────────────┘

Usage :
    from engine.scouting_card import generate_scouting_card
    img_bytes = generate_scouting_card(player_dict, df_all_players)
    # → bytes PNG téléchargeable via Streamlit
"""

from __future__ import annotations

import io
import math
import ast
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import numpy as np


# ─── Palette ───────────────────────────────────────────────────────────────
TIER_CONFIG = [
    (90, "#FFD700", "#0D0800", "LÉGENDAIRE"),
    (84, "#C8A840", "#080F20", "OR"),
    (77, "#3A7A28", "#080E08", "ARGENT"),
    (70, "#8C4020", "#120808", "BRONZE"),
    (0,  "#585858", "#141414", "STANDARD"),
]

AXIS_LABELS = {
    "axis_att":         "CARRY",
    "axis_def":         "DEF",
    "axis_disc":        "DISC",
    "axis_ctrl":        "CTRL",
    "axis_kick":        "KICK",
    "axis_pow":         "DANGER",
    "axis_gabarit":     "GABARIT",
    "axis_consistency": "CONSIST",
}

STAT_LABELS = {
    "tackles_per80":       "Plaquages /80",
    "line_breaks_per80":   "Franchissements /80",
    "offloads_per80":      "Offloads /80",
    "turnovers_won_per80": "Turnovers /80",
    "tries_per80":         "Essais /80",
    "points_scored_per80": "Points /80",
    "matches_played":      "Matchs",
    "minutes_total":       "Minutes",
}


def _tier_for_rating(rating: float) -> tuple[str, str, str]:
    for threshold, color, bg, label in TIER_CONFIG:
        if rating >= threshold:
            return color, bg, label
    return "#585858", "#141414", "STANDARD"


def _radar(ax, values: list[float], labels: list[str],
           color: str, alpha: float = 0.35, label: str = ""):
    n = len(values)
    angles = [i * 2 * math.pi / n for i in range(n)] + [0]
    vals   = values + [values[0]]

    ax.plot(angles, vals, color=color, linewidth=2, label=label)
    ax.fill(angles, vals, color=color, alpha=alpha)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=8, color="#CCCCCC")
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], size=6, color="#666")
    ax.tick_params(axis="both", pad=4)
    ax.spines["polar"].set_color("#444")
    ax.set_facecolor("#1A1A2E")
    ax.yaxis.grid(True, color="#333", linewidth=0.5)
    ax.xaxis.grid(True, color="#333", linewidth=0.5)


def _sparkline(ax, scores: list[float], trend: str, color: str = "#3B82F6"):
    if not scores:
        ax.text(0.5, 0.5, "Pas de données forme", ha="center", va="center",
                color="#888", fontsize=9, transform=ax.transAxes)
        ax.axis("off")
        return

    n = len(scores)
    x = list(range(n))
    avg = float(np.mean(scores))
    bar_colors = [color if s >= avg else "#374151" for s in scores]

    ax.bar(x, scores, color=bar_colors, width=0.7, zorder=3)
    ax.axhline(avg, color="#9CA3AF", linewidth=1, linestyle="--", alpha=0.8)

    x_labels = [f"M-{n-i}" for i in range(n)]
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=7, color="#CCCCCC")
    ax.set_ylim(0, 115)
    ax.set_yticks([])

    for i, s in enumerate(scores):
        ax.text(i, s + 4, f"{s:.0f}", ha="center", va="bottom",
                fontsize=7, color="#DDD")

    trend_color = {"↗": "#10B981", "↘": "#EF4444", "→": "#9CA3AF"}.get(trend, "#9CA3AF")
    ax.text(0.98, 0.96, trend, transform=ax.transAxes, ha="right", va="top",
            fontsize=18, color=trend_color, fontweight="bold")
    ax.set_facecolor("#1A1A2E")
    for spine in ax.spines.values():
        spine.set_color("#333")


def _position_percentiles(ax, player: dict, df_pos: "import pandas as pd; pd.DataFrame",
                          cons_val: float | None = None):
    """Barres horizontales : valeur du joueur vs médiane de poste."""
    stats = [k for k in STAT_LABELS if k in df_pos.columns and player.get(k) is not None][:5]
    if not stats and cons_val is None:
        ax.axis("off")
        return

    import pandas as _pd
    # Ajoute consistance comme barre supplémentaire (déjà en [0,100])
    extra_labels = []
    extra_pcts   = []
    extra_raws   = []
    if cons_val is not None:
        extra_labels.append("Consistance")
        extra_pcts.append(min(100.0, cons_val))
        extra_raws.append(cons_val)

    y = list(range(len(stats) + len(extra_labels)))
    labels = [STAT_LABELS[s] for s in stats] + extra_labels
    player_vals = [float(player.get(s, 0) or 0) for s in stats] + extra_raws
    pos_max = [float(df_pos[s].quantile(0.95)) if s in df_pos.columns else 1.0 for s in stats]

    pcts = [min(100.0, (v / mx * 100) if mx > 0 else 0.0) for v, mx in zip(player_vals[:len(stats)], pos_max)]
    pcts += extra_pcts

    bar_colors = ["#3B82F6"] * len(stats) + (["#A78BFA"] if extra_labels else [])
    bars = ax.barh(y, pcts, color=bar_colors, height=0.6, zorder=3, alpha=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7, color="#CCCCCC")
    ax.set_xlim(0, 115)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0", "25", "50", "75", "100"], fontsize=6, color="#888")
    ax.axvline(50, color="#555", linewidth=0.8, linestyle="--", alpha=0.6)

    for bar, pct, raw in zip(bars, pcts, player_vals):
        ax.text(pct + 1.5, bar.get_y() + bar.get_height() / 2,
                f"{raw:.1f}", va="center", ha="left", fontsize=7, color="#DDD")

    ax.set_facecolor("#1A1A2E")
    for spine in ax.spines.values():
        spine.set_color("#333")
    ax.tick_params(colors="#888")


def generate_scouting_card(
    player: dict,
    df_all: "pd.DataFrame | None" = None,
    dpi: int = 150,
) -> bytes:
    """
    Génère la fiche scouting d'un joueur et retourne les bytes PNG.

    Args:
        player : dict issu de players_scored.csv (une ligne)
        df_all : DataFrame complet pour calculer les percentiles de poste
        dpi    : résolution (150 = bon équilibre qualité/taille)

    Returns:
        bytes PNG téléchargeable
    """
    import pandas as pd

    # ── Layout matplotlib ───────────────────────────────────────────────────
    fig = plt.figure(figsize=(16, 9), facecolor="#0F0F1A")
    gs  = gridspec.GridSpec(
        3, 3,
        figure=fig,
        hspace=0.35,
        wspace=0.3,
        left=0.03, right=0.97, top=0.88, bottom=0.06,
    )

    rating   = float(player.get("display_rating", player.get("rating", 60)) or 60)
    tier_col, tier_bg, tier_lbl = _tier_for_rating(rating)

    # ── HEADER ──────────────────────────────────────────────────────────────
    ax_header = fig.add_axes([0, 0.88, 1, 0.12], facecolor=tier_bg)
    ax_header.axis("off")

    # Badge rating
    ax_header.add_patch(FancyBboxPatch(
        (0.01, 0.1), 0.08, 0.8, transform=ax_header.transAxes,
        boxstyle="round,pad=0.02", facecolor=tier_col + "33",
        edgecolor=tier_col, linewidth=2,
    ))
    ax_header.text(0.05, 0.5, f"{rating:.1f}", transform=ax_header.transAxes,
                   ha="center", va="center", fontsize=28, fontweight="bold",
                   color=tier_col)

    # Nom + infos
    name = player.get("name", "Joueur inconnu")
    pos  = player.get("position_label", player.get("position_group", ""))
    team = player.get("team", "")
    nat  = player.get("nationality", "")
    age  = player.get("age")
    height = player.get("height_cm")
    weight = player.get("weight_kg")

    ax_header.text(0.11, 0.72, name, transform=ax_header.transAxes,
                   ha="left", va="center", fontsize=22, fontweight="bold", color="white")
    sub_parts = [pos, team, nat]
    if age and str(age) not in ("nan", "0", "0.0"):
        sub_parts.append(f"{int(float(age))} ans")
    if height and str(height) not in ("nan", "0", "0.0"):
        sub_parts.append(f"{int(float(height))} cm")
    if weight and str(weight) not in ("nan", "0", "0.0"):
        sub_parts.append(f"{int(float(weight))} kg")
    ax_header.text(0.11, 0.28, "  ·  ".join(p for p in sub_parts if p),
                   transform=ax_header.transAxes,
                   ha="left", va="center", fontsize=11, color="#CCCCCC")

    # Tier badge
    ax_header.add_patch(FancyBboxPatch(
        (0.88, 0.15), 0.10, 0.70, transform=ax_header.transAxes,
        boxstyle="round,pad=0.02", facecolor=tier_col + "22",
        edgecolor=tier_col, linewidth=1.5,
    ))
    ax_header.text(0.93, 0.5, tier_lbl, transform=ax_header.transAxes,
                   ha="center", va="center", fontsize=10, fontweight="bold",
                   color=tier_col)

    # Confiance + forme
    conf  = player.get("confidence", 0.75)
    fscore = player.get("form_score", 50)
    trend  = player.get("form_trend", "→")
    consistency = player.get("axis_consistency")
    try:
        conf   = float(conf)
        fscore = float(fscore)
    except (TypeError, ValueError):
        conf, fscore = 0.75, 50.0
    try:
        cons_val = float(consistency) if consistency not in (None, "", "nan") else None
    except (TypeError, ValueError):
        cons_val = None

    trend_color = {"↗": "#10B981", "↘": "#EF4444", "→": "#9CA3AF"}.get(trend, "#9CA3AF")
    cons_str = f"  ·  Consistance {cons_val:.0f}/100" if cons_val is not None else ""
    info_str = (
        f"Confiance {conf*100:.0f}%  ·  "
        f"Forme {trend} {fscore:.0f}/100  ·  "
        f"{int(player.get('matches_played', 0) or 0)} matchs  ·  "
        f"{int(player.get('minutes_total', player.get('minutes_avg', 0) or 0) or 0)} min"
        f"{cons_str}"
    )
    ax_header.text(0.5, 0.08, info_str, transform=ax_header.transAxes,
                   ha="center", va="center", fontsize=8, color="#9CA3AF")

    # Watermark
    ax_header.text(0.99, 0.92, "RugbyRating.fr — App1", transform=ax_header.transAxes,
                   ha="right", va="top", fontsize=7, color="#555", style="italic")

    # ── Radar Club ──────────────────────────────────────────────────────────
    ax_radar = fig.add_subplot(gs[0:2, 0], projection="polar")
    axes_keys = list(AXIS_LABELS.keys())
    axes_lbls = list(AXIS_LABELS.values())
    vals_club  = [float(player.get(k, 50) or 50) for k in axes_keys]
    _radar(ax_radar, vals_club, axes_lbls, color=tier_col, label="Club (T14)")

    # Overlay radar intl si dispo
    intl_axes_keys = [f"axis_{k}_intl" for k in ["course", "physique", "rigueur", "distrib", "kicking", "danger"]]
    has_intl = any(
        player.get(k) not in (None, "", "nan") and
        str(player.get(k)) != "nan"
        for k in intl_axes_keys
    )
    if has_intl:
        vals_intl = []
        for k in intl_axes_keys:
            v = player.get(k)
            try:
                vals_intl.append(float(v))
            except (TypeError, ValueError):
                vals_intl.append(50.0)
        _radar(ax_radar, vals_intl, axes_lbls, color="#60A5FA", alpha=0.2, label="Intl")

    ax_radar.legend(loc="lower right", fontsize=7, facecolor="#1A1A2E",
                    labelcolor="#CCC", edgecolor="#444")
    ax_radar.set_title("Profil rugby", color="#CCC", fontsize=10, pad=12)

    # ── Sparkline forme ─────────────────────────────────────────────────────
    ax_spark = fig.add_subplot(gs[0, 1])
    spark_raw = player.get("form_scores_list", [])
    if isinstance(spark_raw, str):
        try:
            spark_raw = ast.literal_eval(spark_raw)
        except Exception:
            spark_raw = []
    if not isinstance(spark_raw, list):
        spark_raw = []
    _sparkline(ax_spark, spark_raw, trend, color=tier_col)
    ax_spark.set_title("Forme récente (5 matchs)", color="#CCC", fontsize=10)

    # ── Stats percentiles vs poste ───────────────────────────────────────────
    ax_stats = fig.add_subplot(gs[1, 1])
    if df_all is not None and "position_group" in df_all.columns:
        pg = player.get("position_group", "")
        df_pos = df_all[df_all["position_group"] == pg]
    else:
        df_pos = None

    if df_pos is not None and not df_pos.empty:
        _position_percentiles(ax_stats, player, df_pos, cons_val)
        ax_stats.set_title("Stats vs poste (% du p95)", color="#CCC", fontsize=10)
    else:
        ax_stats.axis("off")
        ax_stats.text(0.5, 0.5, "Stats indisponibles", ha="center", va="center",
                      color="#888", fontsize=9, transform=ax_stats.transAxes)

    # ── Données internationales ──────────────────────────────────────────────
    ax_intl = fig.add_subplot(gs[0:2, 2])
    ax_intl.axis("off")
    ax_intl.set_facecolor("#1A1A2E")

    ri = player.get("rating_intl")
    try:
        ri_val = float(ri) if ri and str(ri) != "nan" else None
    except (TypeError, ValueError):
        ri_val = None

    ax_intl.text(0.5, 0.97, "🌍 Données Internationales", ha="center", va="top",
                 fontsize=11, fontweight="bold", color="#60A5FA",
                 transform=ax_intl.transAxes)

    if ri_val:
        mi   = int(player.get("matches_intl", 0) or 0)
        nation = player.get("team_intl", "")
        delta = ri_val - rating
        ax_intl.text(0.5, 0.82, f"{ri_val:.1f}", ha="center", va="top",
                     fontsize=36, fontweight="bold",
                     color="#60A5FA", transform=ax_intl.transAxes)
        ax_intl.text(0.5, 0.68, f"{nation} · {mi} caps", ha="center", va="top",
                     fontsize=10, color="#9CA3AF", transform=ax_intl.transAxes)
        delta_color = "#10B981" if delta >= 0 else "#EF4444"
        ax_intl.text(0.5, 0.59, f"{delta:+.1f} vs T14", ha="center", va="top",
                     fontsize=11, color=delta_color, fontweight="bold",
                     transform=ax_intl.transAxes)

        # Mini radar intl si axes dispo
        if has_intl:
            intl_lbl_short = ["CARRY", "PHYS", "RIG", "CTRL", "KICK", "DNGR"]
            ax_intl_radar = ax_intl.inset_axes([0.05, 0.05, 0.90, 0.48], projection="polar")
            _radar(ax_intl_radar, vals_intl, intl_lbl_short, color="#60A5FA", alpha=0.25)
            ax_intl_radar.set_xticklabels(intl_lbl_short, size=6, color="#9CA3AF")
    else:
        ax_intl.text(0.5, 0.55, "Pas de données\ninternationales", ha="center", va="center",
                     fontsize=12, color="#555", style="italic", transform=ax_intl.transAxes)

    # ── Tableau stats brutes ─────────────────────────────────────────────────
    ax_table = fig.add_subplot(gs[2, :])
    ax_table.axis("off")
    ax_table.set_facecolor("#12121E")

    stat_cols = [k for k in STAT_LABELS if player.get(k) not in (None, "")]
    table_data = []
    col_headers = []
    for k in stat_cols:
        v = player.get(k)
        try:
            fv = float(v)
            if fv == int(fv):
                table_data.append(str(int(fv)))
            else:
                table_data.append(f"{fv:.1f}")
        except (TypeError, ValueError):
            table_data.append(str(v))
        col_headers.append(STAT_LABELS[k])

    if table_data:
        table = ax_table.table(
            cellText=[table_data],
            colLabels=col_headers,
            cellLoc="center",
            loc="center",
            bbox=[0, 0.1, 1, 0.85],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        for (row, col), cell in table.get_celld().items():
            cell.set_facecolor("#1A1A2E" if row % 2 == 0 else "#12121E")
            cell.set_text_props(color="#CCCCCC")
            cell.set_edgecolor("#333")
            if row == 0:
                cell.set_facecolor("#2D3748")
                cell.set_text_props(color="#9CA3AF", fontweight="bold")

    ax_table.set_title("Statistiques saison 2025-2026", color="#CCC",
                        fontsize=9, loc="left", pad=8)

    # ── Export ──────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()
