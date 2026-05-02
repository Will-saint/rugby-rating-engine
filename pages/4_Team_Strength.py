"""
Page 4 — Force d'équipe et composition XV
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from utils import load_data, load_team_strength, page_config, AXIS_LABELS, season_selector

page_config("Force d'équipe")
st.title("Force des équipes")

season = season_selector("_ts")
df = load_data(season)
ts = load_team_strength(season)

# --- Vue d'ensemble ---
st.subheader("Classement général — Team Strength Score")

fig_ts = px.bar(
    ts.sort_values("team_rating"),
    x="team_rating",
    y="team",
    orientation="h",
    color="team_rating",
    color_continuous_scale="RdYlGn",
    text=ts.sort_values("team_rating")["team_rating"].apply(lambda x: f"{x:.1f}"),
    labels={"team_rating": "Team Strength", "team": ""},
)
fig_ts.update_traces(textposition="outside")
fig_ts.update_layout(
    height=340,
    coloraxis_showscale=False,
    margin=dict(l=10, r=60, t=10, b=10),
)
st.plotly_chart(fig_ts, use_container_width=True)

st.divider()

# --- Radar multi-équipes ---
st.subheader("Radar — profil ATT / DEF / DISC / CTRL / KICK / POW")

axes = ["att_index", "def_index", "kick_index", "pow_index"]
axes_labels = ["Attaque", "Défense", "Jeu au pied", "Puissance"]

# Normalise chaque axe [0, 100] global (min-max joueur) AVANT agrégation par équipe.
# Nécessaire pour axis_disc (médiane=100, p75=100) qui sinon dominerait le radar.
_axis_cols = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]
_axis_minmax: dict = {}  # stocké pour réutilisation dans le mini-radar XV
_df_norm = df[["team"] + _axis_cols].copy()
for _col in _axis_cols:
    _cmin, _cmax = float(_df_norm[_col].min()), float(_df_norm[_col].max())
    _axis_minmax[_col] = (_cmin, _cmax)
    if _cmax > _cmin:
        _df_norm[_col] = (_df_norm[_col] - _cmin) / (_cmax - _cmin) * 100.0
    else:
        _df_norm[_col] = 50.0

team_axes = _df_norm.groupby("team")[_axis_cols].mean().round(1).reset_index()
team_axes.columns = ["team", "ATT", "DEF", "DISC", "CTRL", "KICK", "POW"]


def _norm_val(raw: float, col: str) -> float:
    """Normalise une valeur brute d'axe en [0, 100] avec les min/max globaux."""
    cmin, cmax = _axis_minmax.get(col, (0.0, 100.0))
    if cmax > cmin:
        return max(0.0, min(100.0, (raw - cmin) / (cmax - cmin) * 100.0))
    return 50.0

selected_teams = st.multiselect(
    "Equipes à afficher",
    options=sorted(df["team"].unique().tolist()),
    default=sorted(df["team"].unique().tolist())[:4],
)

if selected_teams:
    radar_labels = ["ATT", "DEF", "DISC", "CTRL", "KICK", "POW"]
    fig_radar = go.Figure()

    colors = ["#EF4444", "#3B82F6", "#10B981", "#F59E0B",
              "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"]

    for i, team_name in enumerate(selected_teams):
        row = team_axes[team_axes["team"] == team_name]
        if row.empty:
            continue
        vals = [float(row[c].values[0]) for c in radar_labels]
        vals_closed = vals + [vals[0]]
        labels_closed = radar_labels + [radar_labels[0]]
        color = colors[i % len(colors)]

        fig_radar.add_trace(go.Scatterpolar(
            r=vals_closed,
            theta=labels_closed,
            fill="toself",
            name=team_name,
            line=dict(color=color, width=2),
        ))

    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=8))),
        legend=dict(x=0.5, y=-0.15, xanchor="center", orientation="h"),
        margin=dict(l=20, r=20, t=20, b=80),
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    try:
        st.plotly_chart(fig_radar, use_container_width=True)
    except Exception as _e:
        st.warning(f"Impossible d'afficher ce graphique : {type(_e).__name__}")

st.divider()

# --- Fiche d'équipe détaillée ---
st.subheader("Fiche équipe — composition du XV")

selected_team = st.selectbox("Sélectionne une équipe", sorted(df["team"].unique()))
team_df = df[df["team"] == selected_team].copy()

# Meilleur joueur par poste
POSITION_ORDER = [
    "FRONT_ROW", "FRONT_ROW", "FRONT_ROW", "LOCK", "LOCK",
    "BACK_ROW", "BACK_ROW", "BACK_ROW",
    "SCRUM_HALF", "FLY_HALF",
    "WINGER", "CENTRE", "CENTRE", "WINGER", "FULLBACK",
]
POSITION_NUMS = list(range(1, 16))

best_xv = []
used_ids = set()

for num, pg in zip(POSITION_NUMS, POSITION_ORDER):
    candidates = team_df[
        (team_df["position_group"] == pg) &
        (~team_df["player_id"].isin(used_ids))
    ]
    if candidates.empty:
        candidates = team_df[~team_df["player_id"].isin(used_ids)]
    if candidates.empty:
        continue
    best = candidates.nlargest(1, "rating").iloc[0]
    used_ids.add(best["player_id"])
    best_xv.append({
        "#": num,
        "Joueur": best["name"],
        "Poste": best.get("position_label", best["position_group"]),
        "Note": round(best["rating"], 1),
        "ATT": int(best["axis_att"]),
        "DEF": int(best["axis_def"]),
        "DISC": int(best["axis_disc"]),
        "CTRL": int(best["axis_ctrl"]),
        "KICK": int(best["axis_kick"]),
        "POW": int(best["axis_pow"]),
    })

xv_df = pd.DataFrame(best_xv)

col_xv, col_ts = st.columns([3, 1])

with col_xv:
    if not xv_df.empty:
        ts_row = ts[ts["team"] == selected_team]
        ts_score = ts_row["team_rating"].values[0] if not ts_row.empty else 0

        st.markdown(f"**Team Strength Score : {ts_score:.1f}**")
        st.dataframe(
            xv_df.style.background_gradient(
                subset=["Note", "ATT", "DEF", "DISC", "CTRL", "KICK", "POW"],
                cmap="YlOrRd",
            ),
            use_container_width=True,
            hide_index=True,
            height=530,
        )

with col_ts:
    if not xv_df.empty:
        # Mini radar de l'équipe — valeurs normalisées [0, 100]
        axes_vals = {
            "ATT":  _norm_val(xv_df["ATT"].mean(),  "axis_att"),
            "DEF":  _norm_val(xv_df["DEF"].mean(),  "axis_def"),
            "DISC": _norm_val(xv_df["DISC"].mean(), "axis_disc"),
            "CTRL": _norm_val(xv_df["CTRL"].mean(), "axis_ctrl"),
            "KICK": _norm_val(xv_df["KICK"].mean(), "axis_kick"),
            "POW":  _norm_val(xv_df["POW"].mean(),  "axis_pow"),
        }
        ks = list(axes_vals.keys())
        vs = list(axes_vals.values())
        vs_c = vs + [vs[0]]
        ks_c = ks + [ks[0]]

        fig_mini = go.Figure(go.Scatterpolar(
            r=vs_c, theta=ks_c, fill="toself",
            line=dict(color="#10B981", width=2),
            fillcolor="rgba(16,185,129,0.2)",
        ))
        fig_mini.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=8))),
            margin=dict(l=10, r=10, t=30, b=10),
            height=280,
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)",
            title=dict(text=selected_team, x=0.5, font=dict(size=11)),
        )
        try:
            st.plotly_chart(fig_mini, use_container_width=True)
        except Exception as _e:
            st.warning(f"Impossible d'afficher ce graphique : {type(_e).__name__}")

        # Indices
        ts_row = ts[ts["team"] == selected_team]
        if not ts_row.empty:
            r = ts_row.iloc[0]
            st.metric("Attack Index", f"{r.get('att_index', 0):.1f}")
            st.metric("Defense Index", f"{r.get('def_index', 0):.1f}")
            st.metric("Kick Index", f"{r.get('kick_index', 0):.1f}")
            st.metric("Power Index", f"{r.get('pow_index', 0):.1f}")
