"""
Rugby Rating Engine — Page d'accueil
"""

import sys
import os
import hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import plotly.express as px
from utils import load_data, load_team_strength, page_config, AXIS_COLORS, load_source_mode, get_available_seasons, nat_flag, rating_to_tier, TIER_COLORS

page_config("Accueil")

# ================================================================
# Hero Section
# ================================================================
st.markdown(
    """
    <div style="
        background: linear-gradient(135deg, #0B1220 0%, #1a0a00 50%, #0F172A 100%);
        border: 1px solid rgba(249,115,22,0.25);
        border-radius: 16px;
        padding: 36px 40px 28px;
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
    ">
      <div style="
          position:absolute;top:0;right:0;width:300px;height:100%;
          background: radial-gradient(ellipse at 80% 50%, rgba(249,115,22,0.12) 0%, transparent 70%);
          pointer-events:none;
      "></div>
      <div style="font-family:'Rajdhani',sans-serif;font-size:0.85em;font-weight:600;
                  letter-spacing:0.2em;color:#F97316;text-transform:uppercase;margin-bottom:6px">
        🏉 Saison 2025-2026 · Top 14
      </div>
      <div style="
          font-family:'Rajdhani',sans-serif;font-weight:700;font-size:3em;
          margin:0 0 8px 0;line-height:1.1;
          background:linear-gradient(90deg,#F97316,#FBBF24,#ffffff);
          -webkit-background-clip:text;-webkit-text-fill-color:transparent;
          background-clip:text;
      ">Rugby Rating Engine</div>
      <p style="color:#94A3B8;font-size:1.05em;margin:0;max-width:560px;line-height:1.5">
        Moteur de notation par poste · Comparaison d'équipes · Prédiction de match · Scouting pro
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ================================================================
# Barre de recherche globale
# ================================================================
with st.container():
    search_query = st.text_input(
        "🔍 Recherche rapide",
        placeholder="Nom d'un joueur (ex : Dupont, Jalibert…)",
        label_visibility="collapsed",
    )
    if search_query and len(search_query) >= 2:
        _df_search = load_data(st.session_state.get("selected_season", "2025-2026"))
        _results = _df_search[_df_search["name"].str.contains(search_query, case=False, na=False)]
        if not _results.empty:
            _results = _results.sort_values("rating", ascending=False).head(8)
            cols_sr = st.columns(min(4, len(_results)))
            for i, (_, row) in enumerate(_results.iterrows()):
                flag = nat_flag(row.get("nationality",""))
                tier = rating_to_tier(row["rating"])
                color = TIER_COLORS[tier]
                with cols_sr[i % 4]:
                    st.markdown(
                        f'<div style="border:1px solid {color};border-radius:8px;padding:8px;margin:2px">'
                        f'<div style="font-weight:bold;font-size:0.95em">{flag} {row["name"]}</div>'
                        f'<div style="color:#9CA3AF;font-size:0.8em">{row["position_group"]} · {row["team"]}</div>'
                        f'<div style="color:{color};font-weight:bold;font-size:1.1em">{row["rating"]:.1f}'
                        f'&nbsp;<span style="font-size:0.75em">{tier}</span></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        elif len(search_query) >= 3:
            st.caption("Aucun joueur trouvé.")

# ================================================================
# Sidebar : gestion du dataset et du cache
# ================================================================
with st.sidebar:
    st.subheader("Saison")

    available_seasons = get_available_seasons()
    if available_seasons:
        selected_season = st.selectbox(
            "Saison", available_seasons[::-1],
            index=0,
            key="global_season",
        )
    else:
        selected_season = "2025-2026"
        st.caption("Saison 2025-2026")

    # Stocker en session_state pour les autres pages
    st.session_state["selected_season"] = selected_season

    st.divider()
    st.subheader("Dataset")

    DATA_MODE = os.environ.get("DATA_MODE", "real")
    SEASON = selected_season
    csv_path = Path(__file__).parent / "data" / "seasons" / selected_season / "players_scored.csv"
    if not csv_path.exists():
        csv_path = Path(__file__).parent / "data" / "players.csv"

    # Infos fichier
    if csv_path.exists():
        file_hash = hashlib.md5(csv_path.read_bytes()).hexdigest()[:8]
        file_date = datetime.fromtimestamp(csv_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        file_size = csv_path.stat().st_size // 1024
        st.caption(f"{csv_path.name} · {file_size} KB")
        st.caption(f"Hash : `{file_hash}` · {file_date}")
    else:
        st.caption("Données introuvables")

    st.caption(f"Mode : `{DATA_MODE}` · Saison : `{SEASON}`")

    st.divider()

    # Bouton vider le cache Streamlit
    if st.button("Vider le cache Streamlit", use_container_width=True,
                 help="Recharge players.csv depuis le disque"):
        st.cache_data.clear()
        st.success("Cache vidé — rechargement...")
        st.rerun()

    # Bouton vider le cache HTTP (scrapers)
    cache_dir = Path(__file__).parent / "data" / "raw" / "html_cache"
    n_cache = len(list(cache_dir.glob("*.html"))) if cache_dir.exists() else 0
    if st.button(f"Vider cache HTTP ({n_cache} pages)", use_container_width=True,
                 help="Supprime les pages HTML mises en cache par les scrapers"):
        if cache_dir.exists():
            for f in cache_dir.glob("*.html"):
                f.unlink()
            st.success(f"{n_cache} fichiers cache supprimés")
        else:
            st.info("Aucun cache HTTP")


# ================================================================
# Chargement des données
# ================================================================
df = load_data(selected_season)
ts = load_team_strength(selected_season)

# ================================================================
# Banner DATA_MODE
# ================================================================
DATA_MODE = os.environ.get("DATA_MODE", "real")

# ================================================================
# Banner SOURCE_MODE (LNR_ONLY vs LNR_SB_MIXED)
# ================================================================
_source_mode = load_source_mode()
if _source_mode == "LNR_ONLY":
    st.error(
        "**SOURCE : LNR UNIQUEMENT** — Les postes sont regroupés (FRONT_ROW / LOCK / BACK_ROW). "
        "Pilier vs Talonneur et Flanker vs N°8 ne sont pas différenciés. "
        "Les stars en sélection nationale (Dupont, Atonio…) peuvent être sous-évaluées faute de données Top14 suffisantes. "
        "Intégrer **Statbunker** pour des postes fins et des stats complètes."
    )
elif _source_mode == "LNR_SB_MIXED":
    st.info(
        "**SOURCE : LNR + Statbunker** — Postes fins disponibles. Couverture stats étendue."
    )

if DATA_MODE == "demo":
    min_conf = int(df["confidence_score"].min()) if "confidence_score" in df.columns else 0
    max_conf = int(df["confidence_score"].max()) if "confidence_score" in df.columns else 100
    st.warning(
        f"**Mode DEMO** — Données synthétiques | "
        f"{len(df)} joueurs · {df['team'].nunique()} équipes · "
        f"Confiance : {min_conf}–{max_conf}% | "
        f"Mode réel : `DATA_MODE=real python run_pipeline.py --season 2023-2024`"
    )
else:
    n_teams = df["team"].nunique()
    n_players = len(df)
    # Couverture sur stats LNR publiques uniquement (stats paywall exclues → ne pas afficher 0%)
    stat_cols = ["tackles_per80", "line_breaks_per80", "offloads_per80",
                 "turnovers_won_per80", "points_scored_per80"]
    available = [c for c in stat_cols if c in df.columns]
    coverage = round(df[available].notna().mean().mean() * 100) if available else 0

    # Infos source
    sources = df["_source"].value_counts().to_dict() if "_source" in df.columns else {}
    source_str = " | ".join(f"{s}:{n}" for s, n in sources.items()) if sources else "LNR"

    st.success(
        f"**Mode RÉEL** — Saison {SEASON} | "
        f"{n_teams} équipes · {n_players} joueurs · "
        f"Stats couverture : ~{coverage}% | "
        f"Sources : {source_str}"
    )

# ================================================================
# KPIs — stat cards visuelles
# ================================================================
_best = df.nlargest(1, "rating").iloc[0]
_kpi_items = [
    ("👤", "Joueurs notés", str(len(df)), "#F97316"),
    ("🏟️", "Équipes", str(df["team"].nunique()), "#3B82F6"),
    ("⭐", "Meilleure note", f"{df['rating'].max():.1f}  —  {_best['name']}", "#10B981"),
    ("📊", "Note moyenne", f"{df['rating'].mean():.1f}", "#8B5CF6"),
]
_kpi_cols = st.columns(4)
for _col, (_icon, _label, _val, _color) in zip(_kpi_cols, _kpi_items):
    with _col:
        st.markdown(
            f"""<div style="
                background:linear-gradient(135deg,{_color}18,{_color}08);
                border:1px solid {_color}44;border-radius:12px;
                padding:16px 18px;position:relative;overflow:hidden;
            ">
              <div style="position:absolute;top:0;left:0;width:3px;height:100%;
                          background:{_color};border-radius:3px 0 0 3px"></div>
              <div style="font-size:1.5em;line-height:1">{_icon}</div>
              <div style="color:#9CA3AF;font-size:0.75em;margin:6px 0 2px;
                          text-transform:uppercase;letter-spacing:0.05em">{_label}</div>
              <div style="font-family:'Rajdhani',sans-serif;font-size:1.35em;
                          font-weight:700;color:{_color}">{_val}</div>
            </div>""",
            unsafe_allow_html=True,
        )

st.divider()

# ================================================================
# Top 10 + Classement équipes
# ================================================================
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("Top 10 joueurs")
    top10 = df.nlargest(10, "rating")[
        ["name", "position_group", "team", "rating",
         "axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]
    ].reset_index(drop=True)
    top10.index = top10.index + 1
    top10.columns = ["Joueur", "Poste", "Equipe", "NOTE",
                     "ATT", "DEF", "DISC", "CTRL", "KICK", "POW"]

    st.dataframe(
        top10.style.background_gradient(subset=["NOTE"], cmap="YlOrRd"),
        use_container_width=True,
        height=370,
    )

with col_right:
    st.subheader("Classement équipes")
    fig_teams = px.bar(
        ts,
        x="team_rating",
        y="team",
        orientation="h",
        color="team_rating",
        color_continuous_scale="Viridis",
        labels={"team_rating": "Team Strength", "team": ""},
        text=ts["team_rating"].apply(lambda x: f"{x:.1f}"),
    )
    fig_teams.update_traces(textposition="outside")
    fig_teams.update_layout(
        height=370,
        margin=dict(l=10, r=30, t=10, b=10),
        coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        showlegend=False,
    )
    try:
        st.plotly_chart(fig_teams, use_container_width=True)
    except Exception as _e:
        st.warning(f"Impossible d'afficher ce graphique : {type(_e).__name__}")

st.divider()

# ================================================================
# Top Movers — écart Note T14 ↔ Note Internationale
# ================================================================
if "rating_intl" in df.columns and df["rating_intl"].notna().any():
    st.subheader("Top Movers — Internationaux sous-utilisés en club")
    st.caption("Joueurs dont la note internationale dépasse significativement leur note Top14 cette saison.")
    _intl = df[df["rating_intl"].notna()].copy()
    _intl["_gap"] = _intl["rating_intl"] - _intl["rating"]
    _movers = _intl.nlargest(10, "_gap").reset_index(drop=True)
    col_mv = st.columns(5)
    for i, row in _movers.iterrows():
        flag = nat_flag(str(row.get("nationality", "")))
        tier_intl = rating_to_tier(float(row["rating_intl"]))
        color = TIER_COLORS[tier_intl]
        _name = str(row["name"])
        _club_r = float(row["rating"])
        _intl_r = float(row["rating_intl"])
        _gap_v  = float(row["_gap"])
        _team_intl = str(row.get("team_intl", "") or "")
        _pos = str(row.get("position_group", "") or "")
        with col_mv[i % 5]:
            st.markdown(
                f'<div style="border:1px solid {color}55;border-radius:10px;padding:10px 8px;'
                f'text-align:center;margin:2px;background:{color}0A">'
                f'<div style="font-size:0.9em;font-weight:700;color:#F1F5F9;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis">{flag} {_name}</div>'
                f'<div style="color:#9CA3AF;font-size:0.7em;margin:2px 0">{_team_intl} &middot; {_pos}</div>'
                f'<div style="margin:6px 0;line-height:1.6">'
                f'<span style="font-size:0.75em;color:#9CA3AF">Club</span><br>'
                f'<span style="font-size:1.1em;font-weight:700;color:#E5E7EB">{_club_r:.1f}</span>'
                f'</div>'
                f'<div style="margin:4px 0;line-height:1.6">'
                f'<span style="font-size:0.75em;color:#9CA3AF">International</span><br>'
                f'<span style="font-size:1.1em;font-weight:700;color:{color}">{_intl_r:.1f}</span>'
                f'</div>'
                f'<div style="background:{color}22;border-radius:6px;padding:3px 6px;margin-top:6px">'
                f'<span style="font-size:1em;font-weight:700;color:#10B981">+{_gap_v:.1f} pts</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.divider()

# ================================================================
# Distribution des ratings par poste
# ================================================================
st.subheader("Distribution des notes par groupe de poste")
fig_box = px.box(
    df,
    x="position_group",
    y="rating",
    color="position_group",
    points="all",
    labels={"position_group": "Poste", "rating": "Note"},
    category_orders={"position_group": [
        "FRONT_ROW", "LOCK", "BACK_ROW",
        "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK"
    ]},
)
fig_box.update_layout(
    showlegend=False,
    margin=dict(l=10, r=10, t=10, b=10),
    height=320,
)
try:
    st.plotly_chart(fig_box, use_container_width=True)
except Exception as _e:
    st.warning(f"Impossible d'afficher ce graphique : {type(_e).__name__}")

st.divider()

# ================================================================
# Couverture des données (mode réel uniquement)
# ================================================================
if DATA_MODE == "real":
    st.subheader("Couverture des données")
    stat_cols_all = [
        "tackles_per80", "tackle_success_pct", "carries_per80", "meters_per80",
        "line_breaks_per80", "offloads_per80", "passes_per80", "kick_meters_per80",
        "points_scored_per80", "penalties_per80", "turnovers_won_per80",
        "ruck_arrivals_per80", "lineout_wins_per80", "scrum_success_pct",
    ]
    available_all = [c for c in stat_cols_all if c in df.columns]
    if available_all:
        cov = df[available_all].notna().mean() * 100
        import pandas as pd
        cov_df = pd.DataFrame({"Métrique": cov.index, "Couverture %": cov.values.round(1)})
        cov_df = cov_df.sort_values("Couverture %")
        fig_cov = px.bar(
            cov_df, x="Couverture %", y="Métrique", orientation="h",
            color="Couverture %", color_continuous_scale="RdYlGn",
            range_color=[0, 100],
            title=f"Couverture des statistiques — Saison {SEASON}",
        )
        fig_cov.add_vline(x=80, line_dash="dash", line_color="orange",
                          annotation_text="Seuil 80%")
        fig_cov.update_layout(
            height=380, coloraxis_showscale=False,
            margin=dict(l=10, r=20, t=50, b=10)
        )
        try:
            st.plotly_chart(fig_cov, use_container_width=True)
        except Exception as _e:
            st.warning(f"Impossible d'afficher ce graphique : {type(_e).__name__}")

        below_80 = cov_df[cov_df["Couverture %"] < 80]
        if not below_80.empty:
            st.info(
                f"{len(below_80)} métriques sous 80% de couverture — "
                f"le moteur utilisera la médiane du poste pour les valeurs manquantes."
            )

st.divider()
st.caption(
    f"Rugby Rating Engine · Dataset : players.csv · "
    f"Saison : {SEASON} · Mode : {DATA_MODE}"
)

# ================================================================
# Section — Top formes du moment + Alertes discipline
# ================================================================
st.divider()
_tab_hot, _tab_cold, _tab_disc = st.tabs(["🔥 En grande forme", "❄️ En difficulté", "🟡 Alertes discipline"])

with _tab_hot:
    st.markdown("**Joueurs avec la meilleure forme récente (5 derniers matchs)**")
    if "form_score" in df.columns and "form_trend" in df.columns:
        _conf_mask_hot = (df["confidence"] >= 0.60) if "confidence" in df.columns else True
        _hot = (
            df[df["form_score"].notna() & _conf_mask_hot]
            .nlargest(12, "form_score")
            [["name","team","position_group","display_rating","form_score","form_trend","matches_played"]]
        )
        _hot_cols = st.columns(3)
        for i, (_, row) in enumerate(_hot.iterrows()):
            with _hot_cols[i % 3]:
                fs     = float(row["form_score"])
                rating = float(row.get("display_rating", row.get("rating", 70)))
                trend  = str(row.get("form_trend", "→"))
                bar_pct = max(0, min(100, int((rating - 40) / 59 * 100)))
                st.markdown(
                    f'<div style="padding:8px;border-radius:8px;background:#1a1a2e;margin:4px 0;'
                    f'border-left:3px solid #10B981">'
                    f'<div style="font-weight:700;font-size:0.9em">{row["name"]}</div>'
                    f'<div style="color:#9CA3AF;font-size:0.75em">{row["position_group"]} · {row["team"]}</div>'
                    f'<div style="margin:4px 0;background:#374151;border-radius:4px;height:6px">'
                    f'<div style="width:{bar_pct}%;background:#10B981;height:6px;border-radius:4px"></div></div>'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<div style="color:#10B981;font-weight:700">{rating:.1f}</div>'
                    f'<div style="color:#9CA3AF;font-size:0.78em">Forme {trend}&nbsp;{fs:.0f}/100</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.caption("Données de forme non disponibles.")

with _tab_cold:
    st.markdown("**Joueurs en baisse de forme (écart form_score vs note saison)**")
    if "form_score" in df.columns:
        _conf_mask_cold = (df["confidence"] >= 0.75) if "confidence" in df.columns else True
        _cold = (
            df[df["form_score"].notna() & _conf_mask_cold]
            .nsmallest(12, "form_score")
            [["name","team","position_group","display_rating","form_score","form_trend","matches_played"]]
        )
        _cold_cols = st.columns(3)
        for i, (_, row) in enumerate(_cold.iterrows()):
            with _cold_cols[i % 3]:
                fs     = float(row["form_score"])
                rating = float(row.get("display_rating", row.get("rating", 70)))
                trend  = str(row.get("form_trend", "→"))
                bar_pct = max(0, min(100, int((rating - 40) / 59 * 100)))
                st.markdown(
                    f'<div style="padding:8px;border-radius:8px;background:#1a1a2e;margin:4px 0;'
                    f'border-left:3px solid #EF4444">'
                    f'<div style="font-weight:700;font-size:0.9em">{row["name"]}</div>'
                    f'<div style="color:#9CA3AF;font-size:0.75em">{row["position_group"]} · {row["team"]}</div>'
                    f'<div style="margin:4px 0;background:#374151;border-radius:4px;height:6px">'
                    f'<div style="width:{bar_pct}%;background:#EF4444;height:6px;border-radius:4px"></div></div>'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<div style="color:#EF4444;font-weight:700">{rating:.1f}</div>'
                    f'<div style="color:#9CA3AF;font-size:0.78em">Forme {trend}&nbsp;{fs:.0f}/100</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.caption("Données de forme non disponibles.")

with _tab_disc:
    st.markdown("**Joueurs avec cartons cette saison (rouge / orange)**")
    _disc_mask = False
    if "red_cards" in df.columns:
        _disc_mask = _disc_mask | (df["red_cards"].fillna(0) > 0)
    if "orange_cards" in df.columns:
        _disc_mask = _disc_mask | (df["orange_cards"].fillna(0) > 0)
    if isinstance(_disc_mask, bool):
        st.caption("Données disciplinaires non disponibles.")
    else:
        _disc_df = df[_disc_mask][["name","team","position_group","display_rating",
                                    "yellow_cards","orange_cards","red_cards","matches_played"]]
        _disc_df = _disc_df.sort_values("red_cards", ascending=False)
        if _disc_df.empty:
            st.success("Aucun carton rouge ou orange cette saison !")
        else:
            import pandas as _pd_disc
            _disc_rename = {"name":"Joueur","team":"Équipe","position_group":"Poste",
                            "display_rating":"Note","yellow_cards":"CJ","orange_cards":"CO",
                            "red_cards":"CR","matches_played":"Matchs"}
            st.dataframe(
                _disc_df.rename(columns=_disc_rename).reset_index(drop=True),
                hide_index=True, use_container_width=True,
            )
