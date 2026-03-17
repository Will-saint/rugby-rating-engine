"""
Page 8 — Historique saisons
Évolution des joueurs et équipes sur toutes les saisons post-COVID (2020-2026).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from utils import page_config, TIER_COLORS, rating_to_tier, get_photo_url, fetch_player_photo_bytes

page_config("Historique Saisons")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_SEASONS_PATH = os.path.join(ROOT, "data", "players_all_seasons.csv")
SEASONS_DIR = os.path.join(ROOT, "data", "seasons")

POST_COVID_SEASONS = ["2020-2021","2021-2022","2022-2023","2023-2024","2024-2025","2025-2026"]

TEAM_COLORS = {
    "Toulouse":    "#8B1A1A", "Bordeaux": "#003087", "Lyon": "#0066CC",
    "La Rochelle": "#C8A200", "Racing 92": "#00ADEF", "Clermont": "#D4A000",
    "Montpellier": "#0061A1", "Toulon": "#D4002B", "Paris": "#003DA5",
    "Castres": "#006B3F", "Pau": "#007A3D", "Bayonne": "#E40046",
    "Perpignan": "#DA0000", "Montauban": "#5C2D91",
}

# ─────────────────────────────────────────────
# Chargement données multi-saisons
# ─────────────────────────────────────────────
@st.cache_data(show_spinner="Chargement historique saisons...", ttl=3600)
def load_all_seasons() -> pd.DataFrame | None:
    if not os.path.exists(ALL_SEASONS_PATH):
        return None
    df = pd.read_csv(ALL_SEASONS_PATH)
    # S'assurer que les saisons sont ordonnées
    season_order = {s: i for i, s in enumerate(POST_COVID_SEASONS)}
    df["season_order"] = df["season"].map(season_order).fillna(99)
    df = df.sort_values(["season_order","name"]).drop(columns=["season_order"])
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_season(season: str) -> pd.DataFrame | None:
    path = os.path.join(SEASONS_DIR, season, "players_scored.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


# ─────────────────────────────────────────────
# Vérifier données disponibles
# ─────────────────────────────────────────────
df_all = load_all_seasons()
available_seasons = []
for s in POST_COVID_SEASONS:
    if os.path.exists(os.path.join(SEASONS_DIR, s, "players_scored.csv")):
        available_seasons.append(s)

st.title("Historique Saisons — Top 14")
st.markdown("Évolution des performances joueurs et équipes depuis la reprise post-COVID.")

if not available_seasons:
    st.warning(
        "Aucune donnée historique disponible.\n\n"
        "Lancer d'abord :\n"
        "```bash\n"
        "python data/scrapers/scrape_all_seasons.py\n"
        "python data/scrapers/combine_seasons.py\n"
        "```"
    )
    st.stop()

st.caption(f"Saisons disponibles : {', '.join(available_seasons)}")

if df_all is None and len(available_seasons) > 0:
    # Construire à la volée
    frames = []
    for s in available_seasons:
        d = load_season(s)
        if d is not None:
            d["season"] = s
            frames.append(d)
    df_all = pd.concat(frames, ignore_index=True) if frames else None

if df_all is None:
    st.error("Impossible de charger les données.")
    st.stop()

# ─────────────────────────────────────────────
# Onglets
# ─────────────────────────────────────────────
tab_player, tab_team, tab_top, tab_compare = st.tabs([
    "👤 Carrière joueur",
    "🏉 Évolution équipe",
    "🏆 Top saison",
    "⚖️ Comparer saisons",
])


# ══════════════════════════════════════════════
# TAB 1 — CARRIÈRE JOUEUR
# ══════════════════════════════════════════════
with tab_player:
    all_names = sorted(df_all["name"].dropna().unique().tolist())

    col_search, col_team_f = st.columns([3, 2])
    with col_search:
        search = st.text_input("Rechercher un joueur", placeholder="Ex: Dupont, Ntamack...")
    with col_team_f:
        team_filter = st.selectbox("Filtrer par équipe", ["Toutes"] + sorted(df_all["team"].dropna().unique().tolist()))

    filtered_names = all_names
    if search:
        filtered_names = [n for n in filtered_names if search.lower() in n.lower()]
    if team_filter != "Toutes":
        players_in_team = df_all[df_all["team"] == team_filter]["name"].unique()
        filtered_names = [n for n in filtered_names if n in players_in_team]

    if not filtered_names:
        st.info("Aucun joueur trouvé.")
    else:
        selected_player = st.selectbox("Joueur", filtered_names)
        player_hist = df_all[df_all["name"] == selected_player].sort_values("season")

        if player_hist.empty:
            st.info("Aucune donnée pour ce joueur.")
        else:
            # Header joueur avec photo
            latest = player_hist.iloc[-1].to_dict()
            photo_url = get_photo_url(latest)
            photo_bytes = fetch_player_photo_bytes(photo_url) if photo_url else None

            tier = rating_to_tier(latest["rating"])
            tcolor = TIER_COLORS[tier]
            team_color = TEAM_COLORS.get(latest.get("team",""), "#EF4444")

            col_ph, col_info = st.columns([1, 4])
            with col_ph:
                if photo_bytes:
                    st.image(photo_bytes, use_container_width=True)
            with col_info:
                st.markdown(
                    f'<h3 style="margin:0">{selected_player}</h3>'
                    f'<p style="color:#9CA3AF;margin:2px 0">'
                    f'{latest.get("position_label", latest.get("position_group",""))} · '
                    f'{latest.get("team","")} · {latest.get("nationality","")}</p>',
                    unsafe_allow_html=True,
                )
                seasons_played = player_hist["season"].tolist()
                st.caption(f"Présent en Top 14 : {', '.join(seasons_played)}")

                # KPIs dernière saison
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Note (dernière saison)", f"{latest['rating']:.1f}")
                k2.metric("Tier", tier)
                k3.metric("Matchs", int(latest.get("matches_played", 0) or 0))
                k4.metric("Plaquages /80", f"{latest.get('tackles_per80', 0) or 0:.1f}")

            st.divider()

            # Graphique évolution note
            st.markdown("**Évolution de la note saison par saison**")

            seasons_x = player_hist["season"].tolist()
            ratings_y = player_hist["rating"].tolist()

            fig_rating = go.Figure()
            fig_rating.add_trace(go.Scatter(
                x=seasons_x, y=ratings_y,
                mode="lines+markers+text",
                name="Note",
                line=dict(color=team_color, width=3),
                marker=dict(size=10, color=team_color, line=dict(color="white", width=2)),
                text=[f"{r:.1f}" for r in ratings_y],
                textposition="top center",
                textfont=dict(size=11, color="white"),
            ))
            # Zones tier
            for tier_thresh, tier_label, tier_c in [
                (90,"LEGENDAIRE","#FFD700"),(84,"OR","#C8A840"),
                (77,"ARGENT","#3A7A28"),(70,"BRONZE","#8C4020"),(0,"STANDARD","#585858")
            ]:
                fig_rating.add_hline(
                    y=tier_thresh, line_dash="dot", line_color=tier_c,
                    annotation_text=tier_label, annotation_position="right",
                    annotation_font=dict(size=9, color=tier_c),
                    opacity=0.4,
                )
            fig_rating.update_layout(
                height=300, margin=dict(l=10,r=80,t=20,b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(range=[40,100], gridcolor="#1F2937"),
                xaxis=dict(gridcolor="#1F2937"),
                showlegend=False,
            )
            st.plotly_chart(fig_rating, use_container_width=True)

            # Évolution stats clés
            stat_cols_avail = [c for c in
                ["tackles_per80","line_breaks_per80","offloads_per80","turnovers_won_per80","points_scored_per80"]
                if c in player_hist.columns and player_hist[c].notna().any()
            ]

            if stat_cols_avail:
                st.markdown("**Évolution des stats clés**")

                stat_labels = {
                    "tackles_per80": "Plaquages /80",
                    "line_breaks_per80": "Franchissements /80",
                    "offloads_per80": "Offloads /80",
                    "turnovers_won_per80": "Turnovers gagnés /80",
                    "points_scored_per80": "Points marqués /80",
                }
                stat_colors = ["#EF4444","#3B82F6","#10B981","#F59E0B","#8B5CF6"]

                fig_stats = go.Figure()
                for i, sc in enumerate(stat_cols_avail):
                    fig_stats.add_trace(go.Scatter(
                        x=player_hist["season"].tolist(),
                        y=player_hist[sc].tolist(),
                        mode="lines+markers",
                        name=stat_labels.get(sc, sc),
                        line=dict(color=stat_colors[i % len(stat_colors)], width=2),
                        marker=dict(size=7),
                    ))
                fig_stats.update_layout(
                    height=300, margin=dict(l=10,r=10,t=20,b=10),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(gridcolor="#1F2937"),
                    xaxis=dict(gridcolor="#1F2937"),
                    legend=dict(x=0.5, y=-0.15, xanchor="center", orientation="h", font=dict(size=10)),
                )
                st.plotly_chart(fig_stats, use_container_width=True)

            # Tableau récap
            st.markdown("**Tableau complet par saison**")
            recap_cols = ["season","team","position_label","matches_played","rating",
                          "tackles_per80","line_breaks_per80","offloads_per80","turnovers_won_per80"]
            recap_cols = [c for c in recap_cols if c in player_hist.columns]
            recap = player_hist[recap_cols].copy()
            recap.columns = [{"season":"Saison","team":"Équipe","position_label":"Poste",
                              "matches_played":"Matchs","rating":"Note",
                              "tackles_per80":"Plq/80","line_breaks_per80":"Franch/80",
                              "offloads_per80":"Off/80","turnovers_won_per80":"TO/80"}.get(c,c)
                             for c in recap_cols]
            st.dataframe(
                recap.style.background_gradient(subset=["Note"] if "Note" in recap.columns else [], cmap="YlOrRd"),
                hide_index=True, use_container_width=True,
            )


# ══════════════════════════════════════════════
# TAB 2 — ÉVOLUTION ÉQUIPE
# ══════════════════════════════════════════════
with tab_team:
    selected_team_hist = st.selectbox(
        "Équipe", sorted(df_all["team"].dropna().unique().tolist()),
        key="team_hist_sel"
    )
    team_hist = df_all[df_all["team"] == selected_team_hist].copy()
    tcolor_hist = TEAM_COLORS.get(selected_team_hist, "#EF4444")

    if team_hist.empty:
        st.info("Aucune donnée pour cette équipe.")
    else:
        # Évolution note moyenne et top 5 par saison
        season_stats = team_hist.groupby("season").agg(
            avg_rating=("rating","mean"),
            n_players=("name","count"),
            avg_tackles=("tackles_per80","mean"),
            avg_line_breaks=("line_breaks_per80","mean"),
            avg_turnovers=("turnovers_won_per80","mean"),
        ).reset_index().sort_values("season")

        fig_team = go.Figure()
        fig_team.add_trace(go.Bar(
            x=season_stats["season"],
            y=season_stats["avg_rating"],
            name="Note moyenne",
            marker=dict(
                color=[f"rgba({int(tcolor_hist[1:3],16)},{int(tcolor_hist[3:5],16)},{int(tcolor_hist[5:7],16)},{0.4 + 0.6*(i/max(len(season_stats)-1,1))})"
                       for i in range(len(season_stats))],
                line=dict(color=tcolor_hist, width=1),
            ),
            text=season_stats["avg_rating"].apply(lambda x: f"{x:.1f}"),
            textposition="outside",
        ))
        fig_team.update_layout(
            title=f"Note moyenne {selected_team_hist} par saison",
            height=280, margin=dict(l=10,r=10,t=50,b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(range=[60,90], gridcolor="#1F2937"),
            xaxis=dict(gridcolor="#1F2937"),
            showlegend=False,
        )
        st.plotly_chart(fig_team, use_container_width=True)

        # Évolution stats défense/attaque
        fig_stats_team = go.Figure()
        for sc, label, color in [
            ("avg_tackles","Plaquages /80","#3B82F6"),
            ("avg_line_breaks","Franchissements /80","#EF4444"),
            ("avg_turnovers","Turnovers /80","#10B981"),
        ]:
            if sc in season_stats.columns:
                fig_stats_team.add_trace(go.Scatter(
                    x=season_stats["season"], y=season_stats[sc],
                    mode="lines+markers", name=label,
                    line=dict(color=color, width=2), marker=dict(size=7),
                ))
        fig_stats_team.update_layout(
            height=280, margin=dict(l=10,r=10,t=20,b=60),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="#1F2937"), xaxis=dict(gridcolor="#1F2937"),
            legend=dict(x=0.5,y=-0.25,xanchor="center",orientation="h",font=dict(size=10)),
        )
        st.plotly_chart(fig_stats_team, use_container_width=True)

        # Meilleurs joueurs de l'équipe saison par saison (note max)
        st.markdown("**Meilleur joueur par saison**")
        best_per_season = (
            team_hist.sort_values("rating", ascending=False)
            .groupby("season").first()
            .reset_index()[["season","name","position_label","rating","tackles_per80"]]
        )
        st.dataframe(best_per_season.rename(columns={
            "season":"Saison","name":"Joueur","position_label":"Poste",
            "rating":"Note","tackles_per80":"Plq/80"
        }), hide_index=True, use_container_width=True)

        st.divider()

        # Joueurs présents plusieurs saisons
        st.markdown("**Joueurs les plus fidèles (saisons dans le club)**")
        loyalty = (
            team_hist.groupby("name")
            .agg(n_seasons=("season","nunique"), seasons_list=("season", lambda x: ", ".join(sorted(x))),
                 avg_rating=("rating","mean"), last_pos=("position_label","last"))
            .reset_index()
            .sort_values("n_seasons", ascending=False)
            .head(15)
        )
        st.dataframe(loyalty.rename(columns={
            "name":"Joueur","n_seasons":"Saisons","seasons_list":"Détail",
            "avg_rating":"Note moy.","last_pos":"Poste"
        }), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 3 — TOP PAR SAISON
# ══════════════════════════════════════════════
with tab_top:
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        sel_season_top = st.selectbox("Saison", available_seasons[::-1], key="top_season")
    with col_s2:
        sel_stat = st.selectbox("Stat", [
            "rating", "tackles_per80", "line_breaks_per80", "offloads_per80",
            "turnovers_won_per80", "points_scored_per80"
        ], format_func=lambda x: {
            "rating": "Note globale", "tackles_per80": "Plaquages /80",
            "line_breaks_per80": "Franchissements /80", "offloads_per80": "Offloads /80",
            "turnovers_won_per80": "Turnovers gagnés /80", "points_scored_per80": "Points marqués /80",
        }[x])

    season_df = df_all[df_all["season"] == sel_season_top].copy()

    if season_df.empty:
        st.info(f"Données manquantes pour {sel_season_top}.")
    else:
        top_season = season_df.dropna(subset=[sel_stat]).nlargest(20, sel_stat)

        st.markdown(f"**Top 20 — {sel_season_top}**")

        # Affichage avec photos style podium
        for rank, (_, p) in enumerate(top_season.iterrows()):
            pdict = p.to_dict()
            photo_url = get_photo_url(pdict)
            tier = rating_to_tier(p["rating"])
            tcolor = TIER_COLORS[tier]
            team = p.get("team","")
            tc = TEAM_COLORS.get(team, "#374151")
            pos = p.get("position_label", p.get("position_group",""))
            val = p[sel_stat]

            # Rang couleur
            rank_color = "#FFD700" if rank==0 else "#C0C0C0" if rank==1 else "#CD7F32" if rank==2 else "#6B7280"
            rank_size = "1.2em" if rank < 3 else "0.95em"

            name = p["name"]
            initials = "".join(w[0].upper() for w in name.split()[:2] if w)

            if photo_url:
                photo_html = (
                    f'<img src="{photo_url}" '
                    f'style="width:44px;height:44px;border-radius:50%;object-fit:cover;border:2px solid {tc}" '
                    f'onerror="this.outerHTML=\'<div style=&quot;width:44px;height:44px;border-radius:50%;'
                    f'background:{tc};display:flex;align-items:center;justify-content:center;'
                    f'color:white;font-weight:bold;font-size:12px;border:2px solid {tc}&quot;>{initials}</div>\'">'
                )
            else:
                photo_html = (
                    f'<div style="width:44px;height:44px;border-radius:50%;background:{tc};'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'color:white;font-weight:bold;font-size:12px;border:2px solid {tc}">{initials}</div>'
                )

            bg = f"rgba({int(tc[1:3],16)},{int(tc[3:5],16)},{int(tc[5:7],16)},0.08)" if rank < 3 else "transparent"

            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:12px;padding:8px 16px;
                    background:{bg};border-radius:8px;margin-bottom:4px;
                    border:1px solid {'rgba(255,215,0,0.3)' if rank==0 else '#1F2937'}">
                  <div style="width:28px;text-align:center;font-weight:700;font-size:{rank_size};
                              color:{rank_color};flex-shrink:0">#{rank+1}</div>
                  <div style="flex-shrink:0">{photo_html}</div>
                  <div style="flex:1;min-width:0">
                    <div style="font-weight:600;color:#F9FAFB;font-size:0.9em">{name}</div>
                    <div style="font-size:0.75em;color:#9CA3AF">{pos} · {team}</div>
                  </div>
                  <div style="text-align:right;flex-shrink:0">
                    <div style="font-size:1.15em;font-weight:700;color:{tcolor}">{val:.1f}</div>
                    <div style="font-size:0.7em;color:#9CA3AF">Note {p['rating']:.1f}</div>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════
# TAB 4 — COMPARER DEUX SAISONS
# ══════════════════════════════════════════════
with tab_compare:
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        season_a = st.selectbox("Saison A", available_seasons[::-1], index=0, key="cmp_a")
    with col_c2:
        default_b = available_seasons[-2] if len(available_seasons) >= 2 else available_seasons[0]
        season_b = st.selectbox("Saison B", available_seasons[::-1],
                                index=available_seasons[::-1].index(default_b) if default_b in available_seasons[::-1] else 0,
                                key="cmp_b")

    df_a = df_all[df_all["season"] == season_a]
    df_b = df_all[df_all["season"] == season_b]

    if df_a.empty or df_b.empty:
        st.info("Une des saisons n'est pas disponible.")
    else:
        # Stats league comparaison
        st.markdown("#### Championnat — comparaison des deux saisons")
        compare_stats = ["rating","tackles_per80","line_breaks_per80","offloads_per80","turnovers_won_per80"]
        compare_labels = ["Note globale","Plaquages /80","Franchissements /80","Offloads /80","Turnovers /80"]

        ka = {s: df_a[s].mean() for s in compare_stats if s in df_a.columns}
        kb = {s: df_b[s].mean() for s in compare_stats if s in df_b.columns}

        stat_cols = st.columns(len(compare_stats))
        for col_ui, sc, lbl in zip(stat_cols, compare_stats, compare_labels):
            va = ka.get(sc)
            vb = kb.get(sc)
            if va is not None and vb is not None:
                delta = va - vb
                col_ui.metric(
                    f"{lbl}",
                    f"{va:.1f} ({season_a})",
                    f"{delta:+.1f} vs {season_b}",
                )

        st.divider()

        # Radar comparaison des deux saisons (axes moyens)
        st.markdown("#### Profil moyen Top 14")
        axes_a = {k: float(df_a[f"axis_{k}"].mean()) for k in ["att","def","disc","ctrl","kick","pow"] if f"axis_{k}" in df_a.columns}
        axes_b = {k: float(df_b[f"axis_{k}"].mean()) for k in ["att","def","disc","ctrl","kick","pow"] if f"axis_{k}" in df_b.columns}

        if axes_a and axes_b:
            ks = list(axes_a.keys())
            ks_labels = [k.upper() for k in ks]
            ks_c = ks_labels + [ks_labels[0]]

            fig_cmp = go.Figure()
            vs_a = [axes_a[k] for k in ks]
            fig_cmp.add_trace(go.Scatterpolar(
                r=vs_a + [vs_a[0]], theta=ks_c, fill="toself", name=season_a,
                line=dict(color="#EF4444",width=2), fillcolor="rgba(239,68,68,0.15)",
            ))
            vs_b = [axes_b[k] for k in ks]
            fig_cmp.add_trace(go.Scatterpolar(
                r=vs_b + [vs_b[0]], theta=ks_c, fill="toself", name=season_b,
                line=dict(color="#3B82F6",width=2), fillcolor="rgba(59,130,246,0.15)",
            ))
            fig_cmp.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[30,75], tickfont=dict(size=8))),
                legend=dict(x=0.5,y=-0.12,xanchor="center",orientation="h"),
                height=350, margin=dict(l=10,r=10,t=20,b=60),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_cmp, use_container_width=True)

        st.divider()

        # Joueurs présents dans les deux saisons — évolution de note
        st.markdown("#### Joueurs présents dans les deux saisons — évolution de note")
        common_ids = set(df_a["lnr_id"].dropna()) & set(df_b["lnr_id"].dropna()) if "lnr_id" in df_a.columns else set()

        if common_ids:
            merged = df_a[df_a["lnr_id"].isin(common_ids)][["lnr_id","name","team","rating"]].merge(
                df_b[df_b["lnr_id"].isin(common_ids)][["lnr_id","rating"]],
                on="lnr_id", suffixes=(f"_{season_a}",f"_{season_b}")
            )
            merged["delta"] = merged[f"rating_{season_a}"] - merged[f"rating_{season_b}"]
            merged = merged.sort_values("delta", ascending=False)

            col_up2, col_dn2 = st.columns(2)
            with col_up2:
                st.markdown(f"**▲ Plus progressé ({season_b} → {season_a})**")
                top_up = merged.head(10)[["name","team",f"rating_{season_b}",f"rating_{season_a}","delta"]]
                top_up.columns = ["Joueur","Équipe",season_b,season_a,"Δ"]
                st.dataframe(top_up.style.applymap(
                    lambda v: "color:#10B981;font-weight:bold" if isinstance(v,float) and v > 0 else "", subset=["Δ"]
                ), hide_index=True, use_container_width=True)
            with col_dn2:
                st.markdown(f"**▼ Plus régressé ({season_b} → {season_a})**")
                top_dn = merged.tail(10)[["name","team",f"rating_{season_b}",f"rating_{season_a}","delta"]]
                top_dn.columns = ["Joueur","Équipe",season_b,season_a,"Δ"]
                st.dataframe(top_dn.style.applymap(
                    lambda v: "color:#EF4444;font-weight:bold" if isinstance(v,float) and v < 0 else "", subset=["Δ"]
                ), hide_index=True, use_container_width=True)
        else:
            # fallback sur le nom
            merged = df_a[["name","team","rating"]].merge(df_b[["name","rating"]], on="name", suffixes=(f"_{season_a}",f"_{season_b}"))
            merged["delta"] = merged[f"rating_{season_a}"] - merged[f"rating_{season_b}"]
            merged = merged.sort_values("delta", ascending=False)
            st.dataframe(merged.head(15).rename(columns={
                "name":"Joueur","team":"Équipe",f"rating_{season_a}":season_a,f"rating_{season_b}":season_b,"delta":"Δ"
            }), hide_index=True, use_container_width=True)
