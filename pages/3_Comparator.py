"""
Page 3 — Comparateur 2 joueurs (radar + stats côte à côte)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from utils import load_data, page_config, AXIS_LABELS, AXIS_COLORS, get_available_positions, season_selector
from engine.card import render_card

page_config("Comparateur")
st.title("Comparateur de joueurs")
st.markdown("Compare deux joueurs sur tous leurs axes — **idéalement même poste**.")

season = season_selector("_cmp")
df = load_data(season)

same_pos_mode = st.toggle("Même poste uniquement (recommandé)", value=True)

positions_list = get_available_positions(df)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("### Joueur A")
    teams_a = ["Toutes"] + sorted(df["team"].unique().tolist())
    team_a = st.selectbox("Equipe A", teams_a, key="ta")
    pos_a = st.selectbox("Poste A", positions_list, key="pa")

    filt_a = df.copy()
    if team_a != "Toutes": filt_a = filt_a[filt_a["team"] == team_a]
    filt_a = filt_a[filt_a["position_group"] == pos_a]
    filt_a = filt_a.sort_values("rating", ascending=False)

    player_a_name = st.selectbox("Joueur A", filt_a["name"].tolist(), key="pna")
    player_a = filt_a[filt_a["name"] == player_a_name].iloc[0].to_dict()

with col_b:
    st.markdown("### Joueur B")
    teams_b = ["Toutes"] + sorted(df["team"].unique().tolist())
    team_b = st.selectbox("Equipe B", teams_b, key="tb")

    if same_pos_mode:
        pos_b_options = [pos_a]
    else:
        pos_b_options = positions_list
    pos_b = st.selectbox("Poste B", pos_b_options, key="pb")

    filt_b = df.copy()
    if team_b != "Toutes": filt_b = filt_b[filt_b["team"] == team_b]
    filt_b = filt_b[filt_b["position_group"] == pos_b]
    filt_b = filt_b.sort_values("rating", ascending=False)

    player_b_name = st.selectbox("Joueur B", filt_b["name"].tolist(), key="pnb")
    player_b = filt_b[filt_b["name"] == player_b_name].iloc[0].to_dict()

if player_a["position_group"] != player_b["position_group"]:
    st.warning(
        f"Comparaison cross-postes : {player_a['position_group']} vs {player_b['position_group']}. "
        "Les axes sont calculés dans le poste — la comparaison directe des valeurs est indicative uniquement."
    )

st.divider()

# --- Cartes côte à côte ---
cc1, cc2, cc_mid = st.columns([1, 1, 2])
with cc1:
    st.image(render_card(player_a), width=280)
with cc2:
    st.image(render_card(player_b), width=280)

with cc_mid:
    # Radar superposé
    axes = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]
    labels = [AXIS_LABELS[a] for a in axes]

    vals_a = [player_a.get(a, 50) for a in axes]
    vals_b = [player_b.get(a, 50) for a in axes]

    def hex_rgba(h: str, a: float = 0.2) -> str:
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        return f"rgba({r},{g},{b},{a})"

    fig_radar = go.Figure()
    for vals, name, color in [
        (vals_a, player_a_name, "#EF4444"),
        (vals_b, player_b_name, "#3B82F6"),
    ]:
        closed_vals = vals + [vals[0]]
        closed_labels = labels + [labels[0]]
        fig_radar.add_trace(go.Scatterpolar(
            r=closed_vals,
            theta=closed_labels,
            fill="toself",
            fillcolor=hex_rgba(color, 0.2),
            line=dict(color=color, width=2.5),
            name=name,
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

# --- Comparaison barre horizontale par axe ---
st.subheader("Duel axe par axe")

import pandas as pd
comp_data = []
for ax, label in AXIS_LABELS.items():
    va = player_a.get(ax, 50)
    vb = player_b.get(ax, 50)
    comp_data.append({
        "Axe": label,
        player_a_name: va,
        player_b_name: vb,
        "Gagnant": player_a_name if va > vb else (player_b_name if vb > va else "Egal"),
    })

comp_df = pd.DataFrame(comp_data)

# Afficher en tuiles
for _, row in comp_df.iterrows():
    va = row[player_a_name]
    vb = row[player_b_name]
    label = row["Axe"]
    winner = row["Gagnant"]

    col_l, col_mid2, col_r = st.columns([2, 3, 2])
    with col_l:
        color_a = "#EF4444" if va >= vb else "#666"
        st.markdown(
            f'<div style="text-align:right;font-weight:bold;color:{color_a}">'
            f'{int(va)} <span style="font-size:0.8em;color:#aaa">{player_a_name.split()[0]}</span></div>',
            unsafe_allow_html=True,
        )
    with col_mid2:
        pct_a = int(va / (va + vb) * 100) if (va + vb) > 0 else 50
        st.markdown(
            f'<div style="background:#333;border-radius:6px;overflow:hidden;height:22px;margin-top:4px">'
            f'<div style="width:{pct_a}%;background:#EF4444;height:100%;display:inline-block;'
            f'border-radius:6px 0 0 6px"></div>'
            f'<div style="width:{100-pct_a}%;background:#3B82F6;height:100%;display:inline-block;'
            f'border-radius:0 6px 6px 0"></div>'
            f'</div>'
            f'<div style="text-align:center;font-size:0.8em;color:#aaa;margin-top:2px">{label}</div>',
            unsafe_allow_html=True,
        )
    with col_r:
        color_b = "#3B82F6" if vb >= va else "#666"
        st.markdown(
            f'<div style="font-weight:bold;color:{color_b}">'
            f'<span style="font-size:0.8em;color:#aaa">{player_b_name.split()[0]}</span> {int(vb)}</div>',
            unsafe_allow_html=True,
        )

st.divider()

# --- Stats numériques brutes ---
st.subheader("Stats brutes comparées")
stat_keys = [
    "tackles_per80", "tackle_success_pct", "penalties_per80",
    "turnovers_won_per80", "turnovers_lost_per80", "carries_per80",
    "meters_per80", "line_breaks_per80", "offloads_per80",
    "passes_per80", "kick_meters_per80", "points_scored_per80",
]
labels_map = {
    "tackles_per80": "Plaquages /80", "tackle_success_pct": "% Plaquages",
    "penalties_per80": "Pénalités /80", "turnovers_won_per80": "TO gagnés /80",
    "turnovers_lost_per80": "TO perdus /80", "carries_per80": "Courses /80",
    "meters_per80": "Mètres /80", "line_breaks_per80": "Franchissements /80",
    "offloads_per80": "Offloads /80", "passes_per80": "Passes /80",
    "kick_meters_per80": "Mètres au pied /80", "points_scored_per80": "Points /80",
}
negative_stats = {"penalties_per80", "turnovers_lost_per80"}

raw_rows = []
for k in stat_keys:
    if k not in player_a or k not in player_b:
        continue
    va, vb = round(float(player_a[k]), 1), round(float(player_b[k]), 1)
    if k in negative_stats:
        winner = player_a_name if va < vb else (player_b_name if vb < va else "Egal")
    else:
        winner = player_a_name if va > vb else (player_b_name if vb > va else "Egal")
    raw_rows.append({
        "Stat": labels_map.get(k, k),
        player_a_name: va,
        player_b_name: vb,
        "Avantage": winner,
    })

raw_df = pd.DataFrame(raw_rows)

def highlight_winner(row):
    styles = [""] * len(row)
    col_a_idx = raw_df.columns.get_loc(player_a_name)
    col_b_idx = raw_df.columns.get_loc(player_b_name)
    if row["Avantage"] == player_a_name:
        styles[col_a_idx] = "background-color: rgba(239,68,68,0.2); font-weight:bold"
    elif row["Avantage"] == player_b_name:
        styles[col_b_idx] = "background-color: rgba(59,130,246,0.2); font-weight:bold"
    return styles

st.dataframe(
    raw_df.style.apply(highlight_winner, axis=1),
    use_container_width=True,
    hide_index=True,
)
