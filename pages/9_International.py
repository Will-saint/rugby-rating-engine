"""
Page 9 — Classements Internationaux
Données : Naim (M2PSTB) — ESPN Tests 2016-2024
7 axes : Course, Distribution, Kicking, Physique, Rigueur, Danger, Mêlée
1 195 joueurs, 20 nations
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import page_config

page_config("International")

# ---------------------------------------------------------------------------
# Chargement données
# ---------------------------------------------------------------------------

INTL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "international_ratings.csv")

@st.cache_data(ttl=3600)
def load_intl() -> pd.DataFrame:
    df = pd.read_csv(INTL_PATH)
    return df


try:
    df = load_intl()
except FileNotFoundError:
    st.error("Fichier `data/international_ratings.csv` introuvable.")
    st.stop()

# ---------------------------------------------------------------------------
# En-tête
# ---------------------------------------------------------------------------

st.title("Classements Internationaux")
st.markdown(
    "**Source :** Analyse Naim (M2PSTB) — ESPN Tests 2016–2024 · "
    f"**{len(df):,} joueurs** · 20 nations · 7 axes (Naim methodology)"
)
st.info(
    "Ces notes mesurent la **performance en tests internationaux** (6 Nations, Coupe du Monde, "
    "Rugby Championship…). Elles incluent les passes, mètres, carries — métriques indisponibles "
    "en Top14 public. L'axe Mêlée est unique à ce dataset.",
    icon="ℹ️",
)

# ---------------------------------------------------------------------------
# Onglets
# ---------------------------------------------------------------------------

tab_lb, tab_nation, tab_radar, tab_cross = st.tabs([
    "Classement", "Par Nation", "Radar Joueur", "Croisement Top14"
])

AXES = {
    "axis_course":   "Course",
    "axis_distrib":  "Distribution",
    "axis_kicking":  "Kicking",
    "axis_physique": "Physique",
    "axis_rigueur":  "Rigueur",
    "axis_danger":   "Danger",
    "axis_melee":    "Mêlée",
    "rating_intl":   "Note Intl",
}

POS_ORDER = ["SH","FH","W","C","FB","FL","N8","H","P","L"]
POS_LABEL = {
    "SH": "Demi de mêlée", "FH": "Ouvreur", "W": "Ailier",
    "C": "Centre", "FB": "Arrière", "FL": "Flanker",
    "N8": "N°8", "H": "Talonneur", "P": "Pilier", "L": "2e Ligne",
}

NATION_FLAG = {
    "France": "🇫🇷", "All Blacks": "🇳🇿", "Irlande": "🇮🇪",
    "SA": "🇿🇦", "Angleterre": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Australie": "🇦🇺",
    "Argentine": "🇦🇷", "SCOT": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "WALES": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "ITALY": "🇮🇹", "Japon": "🇯🇵", "FIJI": "🇫🇯",
    "SAMOA": "🇼🇸", "TONGA": "🇹🇴", "GEORG": "🇬🇪",
    "Roumanie": "🇷🇴", "URUG": "🇺🇾", "NAMIB": "🇳🇦",
    "Chili": "🇨🇱", "PORT": "🇵🇹",
}

# ================================================================
# Onglet 1 — Classement par poste
# ================================================================
with tab_lb:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sel_pos = st.selectbox(
            "Poste", ["Tous"] + POS_ORDER,
            format_func=lambda x: POS_LABEL.get(x, x) if x != "Tous" else "Tous les postes",
        )
    with col2:
        nations = sorted(df["team"].dropna().unique())
        sel_nation = st.selectbox("Nation", ["Toutes"] + nations)
    with col3:
        sel_cluster = st.selectbox("Niveau", ["Tous", "cluster_1 (Top)", "cluster_0 (Dév.)"])
    with col4:
        show_n = st.slider("Top N", 5, 50, 20)

    view = df.copy()
    if sel_pos != "Tous":
        view = view[view["position_naim"] == sel_pos]
    if sel_nation != "Toutes":
        view = view[view["team"] == sel_nation]
    if "cluster_1" in sel_cluster:
        view = view[view["cluster"] == "cluster_1"]
    elif "cluster_0" in sel_cluster:
        view = view[view["cluster"] == "cluster_0"]

    view = view.nlargest(show_n, "rating_intl").reset_index(drop=True)
    view.index += 1

    flag_col = view["team"].map(NATION_FLAG).fillna("")
    view["Nation"] = flag_col + " " + view["team"].fillna("")

    # Graphique
    fig = px.bar(
        view, x="rating_intl", y="name", orientation="h",
        color="team",
        hover_data=["position_label", "matches_intl", "axis_course", "axis_danger", "axis_melee"],
        labels={"rating_intl": "Note Intl", "name": ""},
        text=view["rating_intl"].apply(lambda x: f"{x:.1f}"),
        height=max(350, show_n * 28),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        coloraxis_showscale=False,
        legend=dict(title="Nation", x=1.01),
        margin=dict(l=10, r=80, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tableau
    display_cols = ["Nation", "position_label", "rating_intl", "axis_course", "axis_distrib",
                    "axis_kicking", "axis_physique", "axis_rigueur", "axis_danger", "axis_melee", "matches_intl"]
    rename_map = {
        "position_label": "Poste", "rating_intl": "Note",
        "axis_course": "Course", "axis_distrib": "Distrib", "axis_kicking": "Kick",
        "axis_physique": "Physique", "axis_rigueur": "Rigueur", "axis_danger": "Danger",
        "axis_melee": "Mêlée", "matches_intl": "Matchs",
    }
    disp = view[[c for c in display_cols if c in view.columns]].rename(columns=rename_map)
    grad = [c for c in ["Note","Course","Distrib","Kick","Physique","Rigueur","Danger","Mêlée"] if c in disp.columns]
    st.dataframe(
        disp.style.background_gradient(subset=grad, cmap="YlOrRd"),
        use_container_width=True,
        height=min(600, show_n * 36 + 40),
    )

# ================================================================
# Onglet 2 — Par Nation
# ================================================================
with tab_nation:
    st.subheader("Comparaison des nations — Profil moyen par axe")

    nations_sel = st.multiselect(
        "Nations à comparer",
        options=sorted(df["team"].dropna().unique()),
        default=["France", "All Blacks", "Irlande", "Angleterre", "SA"],
    )

    if not nations_sel:
        st.info("Sélectionne au moins une nation.")
    else:
        nation_avg = (
            df[df["team"].isin(nations_sel)]
            .groupby("team")[["axis_course","axis_distrib","axis_kicking","axis_physique",
                               "axis_rigueur","axis_danger","axis_melee","rating_intl"]]
            .mean()
            .round(1)
            .reset_index()
        )
        nation_avg["flag"] = nation_avg["team"].map(NATION_FLAG).fillna("")
        nation_avg["Nation"] = nation_avg["flag"] + " " + nation_avg["team"]

        # Radar par nation
        axes_radar = ["axis_course","axis_distrib","axis_kicking","axis_physique","axis_rigueur","axis_danger","axis_melee"]
        axes_labels = ["Course","Distrib","Kicking","Physique","Rigueur","Danger","Mêlée"]

        fig_r = go.Figure()
        colors = px.colors.qualitative.Set2
        for i, (_, row) in enumerate(nation_avg.iterrows()):
            vals = [row[a] for a in axes_radar]
            fig_r.add_trace(go.Scatterpolar(
                r=vals + [vals[0]],
                theta=axes_labels + [axes_labels[0]],
                fill="toself",
                name=row["Nation"],
                line_color=colors[i % len(colors)],
                opacity=0.7,
            ))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=True,
            height=500,
            margin=dict(l=60, r=60, t=40, b=40),
        )
        st.plotly_chart(fig_r, use_container_width=True)

        # Tableau comparatif
        disp_n = nation_avg[["Nation","rating_intl"] + axes_radar].rename(columns={
            "rating_intl": "Note moy.",
            "axis_course": "Course", "axis_distrib": "Distrib", "axis_kicking": "Kicking",
            "axis_physique": "Physique", "axis_rigueur": "Rigueur", "axis_danger": "Danger",
            "axis_melee": "Mêlée",
        })
        grad_n = ["Note moy.","Course","Distrib","Kicking","Physique","Rigueur","Danger","Mêlée"]
        st.dataframe(
            disp_n.style.background_gradient(subset=grad_n, cmap="YlOrRd"),
            use_container_width=True,
        )

# ================================================================
# Onglet 3 — Radar joueur
# ================================================================
with tab_radar:
    st.subheader("Profil individuel — Radar 7 axes")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        nation_f = st.selectbox("Nation", ["Toutes"] + sorted(df["team"].dropna().unique()), key="radar_nat")
        pool = df if nation_f == "Toutes" else df[df["team"] == nation_f]
        player_list = sorted(pool["name"].dropna().unique())
        sel_player = st.selectbox("Joueur", player_list, key="radar_player")
    with col_r2:
        compare_list = ["Aucun"] + [p for p in player_list if p != sel_player]
        compare_player = st.selectbox("Comparer avec", compare_list, key="radar_cmp")

    axes_r = ["axis_course","axis_distrib","axis_kicking","axis_physique","axis_rigueur","axis_danger","axis_melee"]
    axes_l = ["Course","Distrib","Kicking","Physique","Rigueur","Danger","Mêlée"]

    def player_radar(player_name: str, color: str, label: str) -> go.Scatterpolar:
        row = df[df["name"] == player_name].iloc[0]
        vals = [float(row[a]) for a in axes_r]
        return go.Scatterpolar(
            r=vals + [vals[0]], theta=axes_l + [axes_l[0]],
            fill="toself", name=label, line_color=color, opacity=0.75,
        )

    if sel_player in df["name"].values:
        row1 = df[df["name"] == sel_player].iloc[0]
        fig_rad = go.Figure()
        fig_rad.add_trace(player_radar(sel_player, "#1f77b4", sel_player))
        if compare_player != "Aucun" and compare_player in df["name"].values:
            fig_rad.add_trace(player_radar(compare_player, "#ff7f0e", compare_player))
        fig_rad.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=True, height=450,
            margin=dict(l=60, r=60, t=40, b=40),
        )
        st.plotly_chart(fig_rad, use_container_width=True)

        # Fiche joueur
        flag = NATION_FLAG.get(row1.get("team", ""), "")
        st.markdown(f"### {flag} {sel_player} — {row1.get('position_label','')} · {row1.get('team','')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Note Intl", f"{row1['rating_intl']:.1f}")
        c2.metric("Matchs", int(row1.get("matches_intl", 0)))
        c3.metric("Cluster", "Top" if row1.get("cluster") == "cluster_1" else "Dév.")
        c4.metric("Âge", int(row1.get("Age", 0)) if pd.notna(row1.get("Age")) else "N/A")

# ================================================================
# Onglet 4 — Croisement Top14 ↔ International
# ================================================================
with tab_cross:
    st.subheader("Croisement Top14 ↔ International")
    st.markdown(
        "Joueurs présents dans **les deux datasets**. "
        "La note Top14 mesure la saison 2025-2026 en club ; "
        "la note Internationale mesure la carrière en tests (2016–2024)."
    )

    top14_path = os.path.join(os.path.dirname(__file__), "..", "data", "players_scored.csv")
    if not os.path.exists(top14_path):
        st.warning("Données Top14 introuvables.")
    else:
        df_t14 = pd.read_csv(top14_path)

        # Normaliser les noms pour le matching
        def _norm(s: str) -> str:
            import unicodedata
            s = str(s).upper().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            return s

        df["_key"] = df["name"].apply(_norm)
        df_t14["_key"] = df_t14["name"].apply(_norm)

        # Merge sur clé normalisée
        merged = df_t14.merge(
            df[["_key","name","rating_intl","axis_course","axis_distrib","axis_kicking",
                "axis_physique","axis_rigueur","axis_danger","axis_melee","team","position_label","matches_intl"]],
            on="_key", suffixes=("_t14", "_intl"),
        )
        merged = merged.drop(columns=["_key"])

        st.metric("Joueurs matchés", len(merged))

        if merged.empty:
            st.info("Aucun joueur commun trouvé. Les noms sont abrégés différemment entre les deux sources.")
        else:
            # Tri
            sort_by = st.selectbox("Trier par", ["rating_intl", "rating", "rating_value"], index=0)
            if sort_by not in merged.columns:
                sort_by = "rating_intl"
            disp_m = merged.nlargest(50, sort_by)[[
                "name_t14", "team_t14", "position_group",
                "rating", "rating_intl",
                "axis_att", "axis_course",
                "axis_def", "axis_physique",
                "axis_disc", "axis_rigueur",
                "axis_pow", "axis_danger",
                "matches_played", "matches_intl",
            ]].rename(columns={
                "name_t14": "Joueur", "team_t14": "Club", "position_group": "Poste",
                "rating": "Note Top14", "rating_intl": "Note Intl",
                "axis_att": "Course T14", "axis_course": "Course Intl",
                "axis_def": "Physique T14", "axis_physique": "Physique Intl",
                "axis_disc": "Rigueur T14", "axis_rigueur": "Rigueur Intl",
                "axis_pow": "Danger T14", "axis_danger": "Danger Intl",
                "matches_played": "Matchs T14", "matches_intl": "Matchs Intl",
            })

            grad_m = [c for c in ["Note Top14","Note Intl"] if c in disp_m.columns]
            st.dataframe(
                disp_m.style.background_gradient(subset=grad_m, cmap="RdYlGn"),
                use_container_width=True,
                height=500,
            )

            # Scatter Top14 vs International
            if len(merged) > 3:
                r_col = "rating_value" if "rating_value" in merged.columns else "rating"
                fig_sc = px.scatter(
                    merged,
                    x=r_col, y="rating_intl",
                    color="position_group",
                    hover_data=["name_t14", "team_t14", "matches_played", "matches_intl"],
                    labels={r_col: "Note Top14", "rating_intl": "Note Intl", "position_group": "Poste"},
                    title="Corrélation Note Top14 ↔ Note Internationale",
                    trendline="ols",
                )
                st.plotly_chart(fig_sc, use_container_width=True)
