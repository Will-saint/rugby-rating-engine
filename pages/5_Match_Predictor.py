"""
Page 5 — Prédicteur de match
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from utils import load_data, load_team_strength, page_config, season_selector
from engine.predictor import predict_match

page_config("Prédicteur de match")
st.title("Prédicteur de match")
st.markdown(
    "Sélectionne deux équipes et ajuste les paramètres pour obtenir une probabilité de victoire "
    "et un score estimé."
)

season = season_selector("_pred")
df = load_data(season)
ts = load_team_strength(season)

teams = sorted(df["team"].unique().tolist())

# --- Sélection des équipes ---
col_h, col_sep, col_a = st.columns([2, 1, 2])

with col_h:
    st.markdown("### Domicile")
    home_team = st.selectbox("Equipe domicile", teams, key="home")
    home_form = st.slider(
        "Forme récente (domicile)",
        -1.0, 1.0, 0.0, 0.1,
        help="-1 = très mauvaise forme, +1 = excellente forme",
        key="hf",
    )

with col_sep:
    st.markdown("<br><br><br><div style='text-align:center;font-size:2em;font-weight:bold'>VS</div>",
                unsafe_allow_html=True)

with col_a:
    st.markdown("### Extérieur")
    away_team = st.selectbox("Equipe extérieur", [t for t in teams if t != home_team], key="away")
    away_form = st.slider(
        "Forme récente (extérieur)",
        -1.0, 1.0, 0.0, 0.1,
        key="af",
    )

neutral_venue = st.checkbox("Terrain neutre (ex : demi-finale / finale)", value=False)

if home_team == away_team:
    st.warning("Choisissez deux équipes différentes.")
    st.stop()

# --- Récupérer les indices ---
def get_team_row(team_name):
    row = ts[ts["team"] == team_name]
    if row.empty:
        return {"team_rating": 60, "att_index": 50, "def_index": 50,
                "kick_index": 50, "pow_index": 50}
    return row.iloc[0].to_dict()

home_row = get_team_row(home_team)
away_row = get_team_row(away_team)

# --- Prédiction ---
pred = predict_match(
    home_rating=home_row["team_rating"],
    away_rating=away_row["team_rating"],
    home_att=home_row.get("att_index", 50),
    home_def=home_row.get("def_index", 50),
    away_att=away_row.get("att_index", 50),
    away_def=away_row.get("def_index", 50),
    home_form=home_form,
    away_form=away_form,
    neutral_venue=neutral_venue,
)

st.divider()

# --- Résultats ---
st.subheader("Prédiction")

# Jauge de probabilité
fig_gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=pred.home_win_pct,
    title={"text": f"% victoire {home_team}", "font": {"size": 14}},
    gauge={
        "axis": {"range": [0, 100]},
        "bar": {"color": "#EF4444"},
        "steps": [
            {"range": [0, 33], "color": "#3B82F6"},
            {"range": [33, 50], "color": "#93C5FD"},
            {"range": [50, 67], "color": "#FCA5A5"},
            {"range": [67, 100], "color": "#EF4444"},
        ],
        "threshold": {
            "line": {"color": "white", "width": 3},
            "thickness": 0.75,
            "value": 50,
        },
    },
))
fig_gauge.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=20))

col_g, col_scores, col_info = st.columns([2, 2, 2])

with col_g:
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_scores:
    st.markdown("#### Score estimé")
    sc1, sc2 = st.columns(2)
    with sc1:
        st.metric(
            home_team.split()[0] if len(home_team.split()) > 1 else home_team,
            f"{pred.expected_home_score:.0f}",
            delta=f"+{pred.predicted_margin:.0f}" if pred.predicted_margin > 0 else None,
        )
    with sc2:
        st.metric(
            away_team.split()[0] if len(away_team.split()) > 1 else away_team,
            f"{pred.expected_away_score:.0f}",
            delta=f"+{-pred.predicted_margin:.0f}" if pred.predicted_margin < 0 else None,
        )

    st.markdown("#### Probabilités")
    prob_df = pd.DataFrame({
        "Résultat": [home_team, "Nul", away_team],
        "Probabilité %": [pred.home_win_pct, pred.draw_pct, pred.away_win_pct],
    })
    fig_prob = px.bar(
        prob_df, x="Résultat", y="Probabilité %",
        color="Résultat",
        color_discrete_map={
            home_team: "#EF4444",
            "Nul": "#9CA3AF",
            away_team: "#3B82F6",
        },
        text=prob_df["Probabilité %"].apply(lambda x: f"{x:.1f}%"),
    )
    fig_prob.update_traces(textposition="outside")
    fig_prob.update_layout(
        showlegend=False,
        height=200,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_range=[0, 100],
    )
    st.plotly_chart(fig_prob, use_container_width=True)

with col_info:
    st.markdown("#### Analyse du match")
    st.markdown(f"**Confiance du modèle :** {pred.confidence}")

    if pred.risk_flag:
        st.warning("Match à risque — résultat très incertain !")
    elif pred.home_win_pct > 70:
        st.success(f"Favori net : {home_team}")
    elif pred.away_win_pct > 70:
        st.success(f"Favori net : {away_team}")
    else:
        st.info("Match équilibré.")

    st.markdown(f"**Ecart prédit :** {abs(pred.predicted_margin):.0f} pts "
                f"en faveur de {'Domicile' if pred.predicted_margin > 0 else 'Extérieur'}")

    # Team Strength
    st.markdown("#### Forces comparées")
    ts_comp = pd.DataFrame({
        "Equipe": [home_team, away_team],
        "Team Strength": [home_row["team_rating"], away_row["team_rating"]],
        "Attaque": [home_row.get("att_index", 50), away_row.get("att_index", 50)],
        "Défense": [home_row.get("def_index", 50), away_row.get("def_index", 50)],
    })
    st.dataframe(ts_comp, hide_index=True, use_container_width=True)

st.divider()

# --- Analyse poste par poste ---
st.subheader("Analyse poste par poste")

home_players = df[df["team"] == home_team].copy()
away_players = df[df["team"] == away_team].copy()

pos_groups = [
    "FRONT_ROW", "LOCK", "BACK_ROW",
    "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK",
]

pos_comp = []
for pg in pos_groups:
    h = home_players[home_players["position_group"] == pg]
    a = away_players[away_players["position_group"] == pg]
    if h.empty or a.empty:
        continue
    h_best = h.nlargest(1, "rating").iloc[0]
    a_best = a.nlargest(1, "rating").iloc[0]
    pos_comp.append({
        "Poste": pg,
        f"{home_team[:12]}": f"{h_best['name']} ({h_best['rating']:.0f})",
        f"{away_team[:12]}": f"{a_best['name']} ({a_best['rating']:.0f})",
        "Avantage": home_team[:12] if h_best["rating"] > a_best["rating"]
                    else (away_team[:12] if a_best["rating"] > h_best["rating"] else "Egal"),
        "Delta": round(h_best["rating"] - a_best["rating"], 1),
    })

pos_comp_df = pd.DataFrame(pos_comp)

def color_delta(val):
    if val > 3:
        return "color: #10B981; font-weight: bold"
    elif val < -3:
        return "color: #EF4444; font-weight: bold"
    return "color: #9CA3AF"

st.dataframe(
    pos_comp_df.style.map(color_delta, subset=["Delta"]),
    hide_index=True,
    use_container_width=True,
)

# Bar chart du delta
fig_delta = px.bar(
    pos_comp_df,
    x="Poste",
    y="Delta",
    color="Delta",
    color_continuous_scale="RdYlGn",
    title=f"Avantage par poste : {home_team} (positif) vs {away_team} (négatif)",
    labels={"Delta": "Ecart de note"},
)
fig_delta.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
fig_delta.update_layout(
    height=300,
    margin=dict(l=10, r=10, t=50, b=10),
    coloraxis_showscale=False,
)
st.plotly_chart(fig_delta, use_container_width=True)
