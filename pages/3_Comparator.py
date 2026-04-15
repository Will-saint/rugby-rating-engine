"""
Page 3 — Comparateur jusqu'à 3 joueurs (radar + stats + sparkline forme)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from utils import load_data, page_config, AXIS_LABELS, AXIS_COLORS, get_available_positions, season_selector
from engine.card import render_card

page_config("Comparateur")
st.title("Comparateur de joueurs")
st.markdown(
    "Compare **jusqu'à 3 joueurs** sur tous leurs axes. "
    "La sparkline montre la forme des 5 derniers matchs."
)

season = season_selector("_cmp")
df = load_data(season)

same_pos_mode = st.toggle("Même poste uniquement (recommandé)", value=True)
three_players  = st.toggle("Ajouter un 3ème joueur", value=False)

positions_list = get_available_positions(df)

PLAYER_COLORS = ["#EF4444", "#3B82F6", "#10B981"]
PLAYER_LABELS = ["Joueur A", "Joueur B", "Joueur C"]


def player_selector(col_key: str, color: str, label: str, pos_constraint: str | None = None) -> dict | None:
    st.markdown(f'<span style="color:{color}; font-weight:700; font-size:1.05em">● {label}</span>',
                unsafe_allow_html=True)
    teams = ["Toutes"] + sorted(df["team"].unique().tolist())
    team  = st.selectbox("Équipe", teams, key=f"team_{col_key}")
    pos_options = [pos_constraint] if (same_pos_mode and pos_constraint) else positions_list
    pos   = st.selectbox("Poste", pos_options, key=f"pos_{col_key}")
    filt  = df.copy()
    if team != "Toutes":
        filt = filt[filt["team"] == team]
    filt = filt[filt["position_group"] == pos].sort_values("display_rating", ascending=False)
    if filt.empty:
        st.caption("Aucun joueur trouvé.")
        return None
    name = st.selectbox("Joueur", filt["name"].tolist(), key=f"name_{col_key}")
    return filt[filt["name"] == name].iloc[0].to_dict()


n_cols = 3 if three_players else 2
cols = st.columns(n_cols)

players: list[dict | None] = []
pos_a = None
with cols[0]:
    p = player_selector("a", PLAYER_COLORS[0], PLAYER_LABELS[0])
    players.append(p)
    if p:
        pos_a = p.get("position_group")

with cols[1]:
    p = player_selector("b", PLAYER_COLORS[1], PLAYER_LABELS[1], pos_constraint=pos_a)
    players.append(p)

if three_players:
    with cols[2]:
        p = player_selector("c", PLAYER_COLORS[2], PLAYER_LABELS[2], pos_constraint=pos_a)
        players.append(p)

active = [(pl, PLAYER_COLORS[i], PLAYER_LABELS[i]) for i, pl in enumerate(players) if pl is not None]
if len(active) < 2:
    st.info("Sélectionne au moins 2 joueurs pour comparer.")
    st.stop()

# Cross-poste warning
pos_groups = {pl["position_group"] for pl, _, _ in active}
if len(pos_groups) > 1:
    st.warning(
        "Comparaison cross-postes : " + " vs ".join(pos_groups) +
        ". Les axes sont calculés dans le poste — les valeurs sont indicatives."
    )

st.divider()

# ============================================================
# Cartes + Radar principal
# ============================================================
card_cols = st.columns([1] * len(active) + [2])

for i, (pl, color, label) in enumerate(active):
    with card_cols[i]:
        st.image(render_card(pl), use_container_width=True)
        # Form trend badge
        trend  = pl.get("form_trend", "→")
        fmatches = int(pl.get("form_matches", 0) or 0)
        fscore = pl.get("form_score", 50)
        try:
            fscore = float(fscore)
        except (TypeError, ValueError):
            fscore = 50.0
        trend_color = {"↗": "#10B981", "↘": "#EF4444", "→": "#9CA3AF"}.get(trend, "#9CA3AF")
        st.markdown(
            f'<div style="text-align:center; margin-top:-8px">'
            f'<span style="color:{trend_color}; font-size:1.3em; font-weight:700">{trend}</span>'
            f'<span style="color:#9CA3AF; font-size:0.8em"> forme {fmatches}M · {fscore:.0f}/100</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

with card_cols[-1]:
    axes   = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]
    labels = [AXIS_LABELS[a] for a in axes]

    def hex_rgba(h: str, a: float = 0.2) -> str:
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        return f"rgba({r},{g},{b},{a})"

    fig_radar = go.Figure()
    for pl, color, label in active:
        vals   = [float(pl.get(a, 50) or 50) for a in axes]
        closed = vals + [vals[0]]
        fig_radar.add_trace(go.Scatterpolar(
            r=closed,
            theta=labels + [labels[0]],
            fill="toself",
            fillcolor=hex_rgba(color, 0.18),
            line=dict(color=color, width=2.5),
            name=pl["name"],
        ))

    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100]),
            angularaxis=dict(tickfont=dict(size=11)),
        ),
        legend=dict(x=0.5, y=-0.15, xanchor="center", orientation="h"),
        margin=dict(l=20, r=20, t=20, b=50),
        height=380,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_radar, use_container_width=True)

st.divider()

# ============================================================
# Sparklines de forme (5 derniers matchs)
# ============================================================
st.subheader("Forme récente — 5 derniers matchs")

any_spark = any(pl.get("form_scores_list") for pl, _, _ in active)
if not any_spark:
    st.caption("Données de forme non disponibles (match history absent ou joueur < 5 matchs).")
else:
    spark_cols = st.columns(len(active))
    for i, (pl, color, label) in enumerate(active):
        with spark_cols[i]:
            scores = pl.get("form_scores_list")
            if isinstance(scores, str):
                import ast
                try:
                    scores = ast.literal_eval(scores)
                except Exception:
                    scores = []
            if not scores:
                st.caption(f"{pl['name']} — pas de données de forme.")
                continue
            fig_spark = go.Figure()
            x_labels = [f"M-{len(scores)-j}" for j in range(len(scores))]
            fig_spark.add_trace(go.Bar(
                x=x_labels,
                y=scores,
                marker_color=[
                    color if s >= np.mean(scores) else "#374151"
                    for s in scores
                ],
                text=[f"{s:.0f}" for s in scores],
                textposition="outside",
            ))
            fig_spark.add_hline(
                y=float(np.mean(scores)),
                line_dash="dot",
                line_color="#9CA3AF",
                annotation_text="moy",
                annotation_position="bottom right",
            )
            trend = pl.get("form_trend", "→")
            trend_color = {"↗": "#10B981", "↘": "#EF4444", "→": "#9CA3AF"}.get(trend, "#9CA3AF")
            fig_spark.update_layout(
                title=dict(
                    text=f'<span style="color:{trend_color}">{trend}</span> {pl["name"]}',
                    x=0, font=dict(size=13),
                ),
                height=200,
                margin=dict(l=5, r=5, t=30, b=5),
                yaxis=dict(range=[0, 110], showticklabels=False),
                xaxis=dict(showticklabels=True),
                showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_spark, use_container_width=True)

st.divider()

# ============================================================
# Section Internationale
# ============================================================
intl_axes   = ["axis_course_intl","axis_distrib_intl","axis_kicking_intl",
               "axis_physique_intl","axis_rigueur_intl","axis_danger_intl","axis_melee_intl"]
intl_labels = ["Course","Distrib","Kicking","Physique","Rigueur","Danger","Mêlée"]

def safe_float(v):
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None

has_any_intl = any(
    any(safe_float(pl.get(a)) is not None for a in intl_axes)
    for pl, _, _ in active
)

if has_any_intl:
    st.subheader("Profil International (données Naim — ESPN Tests 2016–2024)")
    intl_metric_cols = st.columns(len(active))
    for i, (pl, color, label) in enumerate(active):
        with intl_metric_cols[i]:
            ri = safe_float(pl.get("rating_intl"))
            if ri:
                mi = int(pl.get("matches_intl") or 0)
                delta_val = ri - float(pl.get("rating", ri))
                st.metric(
                    f"{pl['name']} — Intl",
                    f"{ri:.1f}",
                    delta=f"{delta_val:+.1f} vs T14",
                )
                st.caption(f"🌍 {pl.get('team_intl','')} · {mi} caps")
            else:
                st.caption(f"_{pl['name']} : pas de données intl_")

    fig_intl = go.Figure()
    for pl, color, label in active:
        if not any(safe_float(pl.get(a)) is not None for a in intl_axes):
            continue
        vals   = [safe_float(pl.get(a)) or 50 for a in intl_axes]
        closed = vals + [vals[0]]
        fig_intl.add_trace(go.Scatterpolar(
            r=closed, theta=intl_labels + [intl_labels[0]],
            fill="toself",
            fillcolor=hex_rgba(color, 0.15),
            line=dict(color=color, width=2),
            name=f"{pl['name']} (Intl)",
        ))
    fig_intl.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        legend=dict(x=0.5, y=-0.1, xanchor="center", orientation="h"),
        margin=dict(l=20, r=20, t=20, b=40),
        height=350,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_intl, use_container_width=True)
    st.divider()

# ============================================================
# Duel axe par axe
# ============================================================
st.subheader("Duel axe par axe")

for ax, ax_label in AXIS_LABELS.items():
    vals = [float(pl.get(ax, 50) or 50) for pl, _, _ in active]
    max_v = max(vals)
    row_cols = st.columns([1.5] + [2] * len(active))
    with row_cols[0]:
        st.markdown(
            f'<div style="margin-top:6px; color:#9CA3AF; font-size:0.85em">{ax_label}</div>',
            unsafe_allow_html=True,
        )
    for j, ((pl, color, _), v) in enumerate(zip(active, vals)):
        with row_cols[j + 1]:
            is_best = v == max_v and len(set(vals)) > 1
            bar_color = color if is_best else "#374151"
            pct = int(v)
            st.markdown(
                f'<div style="background:#1F2937; border-radius:6px; overflow:hidden; height:20px; margin-top:4px">'
                f'<div style="width:{pct}%; background:{bar_color}; height:100%; border-radius:6px"></div>'
                f'</div>'
                f'<div style="font-size:0.78em; color:{"#fff" if is_best else "#9CA3AF"}; '
                f'font-weight:{"700" if is_best else "400"}; margin-top:1px">'
                f'{pl["name"].split()[0]} {int(v)}'
                f'</div>',
                unsafe_allow_html=True,
            )

st.divider()

# ============================================================
# Stats brutes comparées
# ============================================================
st.subheader("Stats brutes comparées")
stat_keys = [
    "tackles_per80", "line_breaks_per80", "offloads_per80",
    "turnovers_won_per80", "points_scored_per80", "tries_per80",
    "yellow_cards", "orange_cards", "red_cards",
    "minutes_total", "matches_played",
]
labels_map = {
    "tackles_per80":       "Plaquages /80",
    "line_breaks_per80":   "Franchissements /80",
    "offloads_per80":      "Offloads /80",
    "turnovers_won_per80": "Ballons grattés /80",
    "points_scored_per80": "Points /80",
    "tries_per80":         "Essais /80",
    "yellow_cards":        "Cartons jaunes",
    "orange_cards":        "Cartons oranges",
    "red_cards":           "Cartons rouges",
    "minutes_total":       "Minutes totales",
    "matches_played":      "Matchs joués",
}
negative_stats = {"yellow_cards", "orange_cards", "red_cards"}

raw_rows = []
for k in stat_keys:
    vals_k = []
    for pl, _, _ in active:
        try:
            vals_k.append(round(float(pl.get(k, 0) or 0), 1))
        except (TypeError, ValueError):
            vals_k.append(0.0)
    if k in negative_stats:
        winner_idx = int(np.argmin(vals_k))
    else:
        winner_idx = int(np.argmax(vals_k))
    row = {"Stat": labels_map.get(k, k)}
    for j, (pl, _, _) in enumerate(active):
        row[pl["name"]] = vals_k[j]
    row["Avantage"] = active[winner_idx][0]["name"]
    raw_rows.append(row)

raw_df = pd.DataFrame(raw_rows)

def highlight_winner(row):
    styles = [""] * len(row)
    for j, (pl, color, _) in enumerate(active):
        col_idx = raw_df.columns.get_loc(pl["name"])
        if row["Avantage"] == pl["name"]:
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            styles[col_idx] = f"background-color: rgba({r},{g},{b},0.2); font-weight:bold"
    return styles

st.dataframe(
    raw_df.style.apply(highlight_winner, axis=1),
    use_container_width=True,
    hide_index=True,
)
