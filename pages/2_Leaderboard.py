"""
Page 2 — Classements par poste
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.express as px
import pandas as pd
from utils import load_data, page_config, TIER_COLORS, rating_to_tier, AXIS_DESCRIPTIONS, get_available_positions, load_source_mode, season_selector, rating_mode_selector, nat_flag

page_config("Classements")
st.title("Classements par poste")
st.markdown(
    "Les notes sont calculées **par poste** (Z-scores intra-poste). "
    "Un classement cross-postes n'a de sens que si les notes sont normalisées — "
    "c'est le cas ici grâce à la calibration FIFA."
)

season   = season_selector("_lb")
sort_col = rating_mode_selector("_lb")
df       = load_data(season)

_source_mode = load_source_mode()
if _source_mode == "LNR_ONLY":
    st.error(
        "**LNR UNIQUEMENT** — Postes regroupés. Stars en sélection nationale peuvent apparaître "
        "sous-classées (flag DATA_INSUFFICIENT si < 5 matchs ou confiance < 25%)."
    )

# --- Onglets : Par poste (défaut) / Top global ---
tab_pos, tab_global = st.tabs(["Par poste", "Top global (normalisé)"])

# ================================================================
# Onglet 1 — Classement par poste
# ================================================================
with tab_pos:
    col1, col2 = st.columns(2)
    with col1:
        position_groups = get_available_positions(df)
        sel_pos = st.selectbox("Groupe de poste", position_groups, index=0)
    with col2:
        teams = ["Toutes"] + sorted(df["team"].unique().tolist())
        sel_team = st.selectbox("Equipe", teams)

    col3, col4, col5 = st.columns(3)
    with col3:
        show_n = st.slider("Nombre de joueurs affichés", 5, 50, 20)
    with col4:
        min_minutes = st.slider(
            "Minutes moyennes min.", 0, 80, 0, 5,
            help="Filtre les joueurs avec peu de temps de jeu",
        )
    with col5:
        show_raw = st.toggle(
            "Note brute",
            value=False,
            key="raw_toggle_pos",
            help="Affiche le score avant shrinkage — ignore le volume de jeu",
        )

    include_low = st.toggle(
        "Inclure faible confiance ⚠",
        value=False,
        key="low_sample_toggle",
        help="Par défaut les joueurs avec confidence < 40% sont masqués (données insuffisantes)",
    )

    view = df[df["position_group"] == sel_pos].copy()
    if sel_team != "Toutes":
        view = view[view["team"] == sel_team]
    if min_minutes > 0 and "minutes_avg" in view.columns:
        view = view[view["minutes_avg"] >= min_minutes]
    if not include_low and "low_sample" in view.columns:
        view = view[~view["low_sample"]]

    # Priorité : mode sidebar (saison/valeur) puis toggle brut
    active_col = (
        "rating_raw" if (show_raw and "rating_raw" in view.columns)
        else (sort_col if sort_col in view.columns else "rating")
    )
    view = view.nlargest(show_n, active_col).reset_index(drop=True)
    view.index = view.index + 1
    # Enrichir : drapeau + tier badge
    view["_flag"] = view["nationality"].apply(nat_flag)
    view["_label"] = view["_flag"] + " " + view["name"]
    view["_tier"] = view["rating"].apply(rating_to_tier)

    mode_label = {"rating": "Saison", "rating_value": "Valeur", "rating_raw": "Brute"}.get(active_col, "")
    st.subheader(f"Top {show_n} — {sel_pos}  ·  Note {mode_label}")

    chart_col = active_col
    chart_label = {"rating": "Note Saison", "rating_value": "Note Valeur", "rating_raw": "Note brute"}.get(active_col, "Note")
    intl_note = view.get("rating_intl") if "rating_intl" in view.columns else None
    fig = px.bar(
        view,
        x=chart_col,
        y="_label",
        orientation="h",
        color=chart_col,
        color_continuous_scale="RdYlGn",
        hover_data={"team": True, "nationality": True, "axis_att": True, "axis_def": True,
                    "_tier": True, "_label": False, "_flag": False},
        labels={chart_col: chart_label, "_label": ""},
        text=view[chart_col].apply(lambda x: f"{x:.1f}"),
    )
    # Overlay Note Intl (scatter) si disponible
    if intl_note is not None and intl_note.notna().any():
        import plotly.graph_objects as go
        intl_view = view[view["rating_intl"].notna()]
        fig.add_trace(go.Scatter(
            x=intl_view["rating_intl"],
            y=intl_view["_label"],
            mode="markers",
            marker=dict(symbol="diamond", size=9, color="#60A5FA", line=dict(color="#1D4ED8", width=1)),
            name="🌍 Note Intl",
            hovertemplate="%{x:.1f} Intl<extra></extra>",
        ))
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=max(300, show_n * 28),
        yaxis=dict(categoryorder="total ascending"),
        coloraxis_showscale=False,
        margin=dict(l=10, r=60, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Explication des axes
    with st.expander("Comprendre les 6 axes de notation"):
        cols_ax = st.columns(3)
        for i, (ax_key, ax_info) in enumerate(AXIS_DESCRIPTIONS.items()):
            with cols_ax[i % 3]:
                st.markdown(f"**{ax_info['emoji']} {ax_info['label']}**")
                st.markdown("Métriques : " + ", ".join(ax_info["metrics"]))
                st.caption(ax_info["note"])

    # Tableau
    extra_cols = []
    if "rank_position" in view.columns:
        extra_cols.append("rank_position")
    if "confidence_badge" in view.columns:
        extra_cols.append("confidence_badge")
    if "confidence_score" in view.columns:
        extra_cols.append("confidence_score")
    if "matches_played" in view.columns:
        extra_cols.append("matches_played")
    if "minutes_bucket" in view.columns:
        extra_cols.append("minutes_bucket")
    if "data_insufficient" in view.columns:
        extra_cols.append("data_insufficient")
    if "rating_raw" in view.columns:
        extra_cols.append("rating_raw")
    if "rating_value" in view.columns:
        extra_cols.append("rating_value")
    if "has_prior" in view.columns:
        extra_cols.append("has_prior")
    has_intl = "rating_intl" in view.columns and view["rating_intl"].notna().any()
    intl_extra = ["rating_intl", "team_intl"] if has_intl else []
    # Construire colonne drapeau + tier pour le tableau
    view["Drapeau"] = view["_flag"]
    view["Tier"] = view["_tier"]
    display_cols = ["Drapeau", "name", "team", "nationality", "Tier", "rating"] + extra_cols + intl_extra + [
        "axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"
    ]
    col_labels = {
        "name": "Joueur", "team": "Equipe", "nationality": "Nationalité",
        "rating": "Note Saison", "rating_raw": "Note brute",
        "rating_value": "Note Valeur", "has_prior": "Prior ?",
        "confidence_badge": "Confiance", "confidence_score": "Confiance %",
        "matches_played": "Matchs", "minutes_bucket": "Temps jeu",
        "data_insufficient": "DATA?", "rank_position": "Rang",
        "rating_intl": "🌍 Note Intl", "team_intl": "Sélection",
        "Drapeau": "🏳️", "Tier": "Tier",
        "axis_att": "Course", "axis_def": "Physique", "axis_disc": "Rigueur",
        "axis_ctrl": "Distrib", "axis_kick": "Kicking", "axis_pow": "Danger",
    }
    display_df = view[[c for c in display_cols if c in view.columns]].rename(columns=col_labels)
    grad_cols = ["Note Saison", "Course", "Physique", "Rigueur", "Distrib", "Kicking", "Danger"]
    if "🌍 Note Intl" in display_df.columns:
        grad_cols.append("🌍 Note Intl")
    if "Confiance %" in display_df.columns:
        grad_cols.append("Confiance %")
    st.dataframe(
        display_df.style.background_gradient(subset=grad_cols, cmap="YlOrRd"),
        use_container_width=True,
        height=min(600, show_n * 36 + 40),
    )
    st.download_button(
        "Exporter CSV",
        data=display_df.to_csv(index=False).encode("utf-8"),
        file_name=f"ratings_{sel_pos}.csv",
        mime="text/csv",
    )

# ================================================================
# Onglet 2 — Top global normalisé par poste
# ================================================================
with tab_global:
    g_col = sort_col if sort_col in df.columns else "rating"
    g_label = "Note Valeur" if g_col == "rating_value" else "Note Saison"
    st.markdown(
        f"**Mode actif : {g_label}** — le classement global compare des joueurs de postes différents "
        "grâce à la calibration Z-score → FIFA (40 + 0.6 × score_final)."
    )
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        show_n_g = st.slider("Nombre de joueurs", 5, 50, 20, key="gn")
    with col_g2:
        min_min_g = st.slider("Minutes moyennes min.", 0, 80, 0, 5, key="gm",
                               help="En mode Valeur, filtrer par minutes est moins utile (prior stabilise)")

    view_g = df.copy()
    if min_min_g > 0 and "minutes_avg" in view_g.columns:
        view_g = view_g[view_g["minutes_avg"] >= min_min_g]
    view_g = view_g.nlargest(show_n_g, g_col).reset_index(drop=True)
    view_g.index = view_g.index + 1
    view_g["_flag_g"] = view_g["nationality"].apply(nat_flag)
    view_g["_label_g"] = view_g["_flag_g"] + " " + view_g["name"]

    fig_g = px.bar(
        view_g,
        x=g_col,
        y="_label_g",
        orientation="h",
        color="position_group",
        hover_data={"position_group": True, "team": True, g_col: True, "_label_g": False, "_flag_g": False},
        labels={g_col: g_label, "_label_g": "", "position_group": "Poste"},
        text=view_g[g_col].apply(lambda x: f"{x:.1f}"),
    )
    fig_g.update_traces(textposition="outside")
    fig_g.update_layout(
        height=max(300, show_n_g * 28),
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(l=10, r=60, t=10, b=10),
        legend=dict(title="Poste", x=1.01),
    )
    st.plotly_chart(fig_g, use_container_width=True)

    g_extra = [g_col] if g_col != "rating" and g_col in view_g.columns else []
    has_intl_g = "rating_intl" in view_g.columns and view_g["rating_intl"].notna().any()
    intl_g_cols = ["rating_intl", "team_intl"] if has_intl_g else []
    g_base_cols = ["name", "position_group", "team", "nationality", "rating"] + g_extra + intl_g_cols + [
        "axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"
    ]
    display_g = view_g[[c for c in g_base_cols if c in view_g.columns]].rename(columns={
        "name": "Joueur", "position_group": "Poste", "team": "Equipe",
        "nationality": "Nationalité", "rating": "Note Saison", "rating_value": "Note Valeur",
        "rating_intl": "🌍 Note Intl", "team_intl": "Sélection",
        "axis_att": "Course", "axis_def": "Physique", "axis_disc": "Rigueur",
        "axis_ctrl": "Distrib", "axis_kick": "Kicking", "axis_pow": "Danger",
    })
    g_grad = [c for c in ["Note Saison", "Note Valeur", "🌍 Note Intl", "Course", "Physique", "Rigueur", "Distrib", "Kicking", "Danger"] if c in display_g.columns]
    st.dataframe(
        display_g.style.background_gradient(subset=g_grad, cmap="YlOrRd"),
        use_container_width=True,
        height=min(600, show_n_g * 36 + 40),
    )

# ================================================================
# Heatmap — qui domine quoi ?
# ================================================================
st.divider()
st.subheader("Heatmap — profil moyen par poste")

axes = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]
axis_names = ["CARRY", "DEF", "DISC", "BRKD", "KICK", "SETP"]
heat_data = df.groupby("position_group")[axes].mean().rename(columns=dict(zip(axes, axis_names))).round(1)

fig_heat = px.imshow(
    heat_data,
    text_auto=True,
    color_continuous_scale="RdYlGn",
    aspect="auto",
    zmin=30, zmax=70,
    labels={"x": "Axe rugby", "y": "Poste", "color": "Score moyen"},
    title="Score moyen par axe et par groupe de poste (percentiles dans le poste)",
)
fig_heat.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(fig_heat, use_container_width=True)
