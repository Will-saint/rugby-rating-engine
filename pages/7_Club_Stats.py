"""
Page 7 — Statistiques Club
Vue complète d'un club, style LNR /club/{slug}/statistiques — avec photos joueurs + métriques propriétaires.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from utils import (
    load_data, load_team_strength, page_config,
    AXIS_LABELS, AXIS_COLORS, rating_to_tier, TIER_COLORS,
    get_photo_url, season_selector,
)

page_config("Stats Club")

# ─────────────────────────────────────────────
# Données
# ─────────────────────────────────────────────
season = season_selector("_club")
df = load_data(season)
ts = load_team_strength(season)

TEAM_COLORS = {
    "Toulouse":    "#8B1A1A",
    "Bordeaux":    "#003087",
    "Lyon":        "#0066CC",
    "La Rochelle": "#C8A200",
    "Racing 92":   "#00ADEF",
    "Clermont":    "#D4A000",
    "Montpellier": "#0061A1",
    "Toulon":      "#D4002B",
    "Paris":       "#003DA5",
    "Castres":     "#006B3F",
    "Pau":         "#007A3D",
    "Bayonne":     "#E40046",
    "Perpignan":   "#DA0000",
    "Montauban":   "#5C2D91",
}

LNR_PHOTO_HASH = "b5e9990d9a31ede8327da9bafe6aeb896ea144f3"

# ─────────────────────────────────────────────
# Helpers HTML
# ─────────────────────────────────────────────

def player_photo_html(player_row: dict, size: int = 52) -> str:
    """Retourne une balise <img> ou un avatar initiales en HTML."""
    url = get_photo_url(player_row)
    name = player_row.get("name", "")
    initials = "".join(w[0].upper() for w in name.split()[:2] if w)
    team = player_row.get("team", "")
    tc = TEAM_COLORS.get(team, "#374151")

    if url:
        return (
            f'<img src="{url}" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;'
            f'object-fit:cover;border:2px solid {tc};background:#1F2937;" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">'
            f'<div style="display:none;width:{size}px;height:{size}px;border-radius:50%;'
            f'background:{tc};color:white;font-weight:bold;font-size:{size//4}px;'
            f'align-items:center;justify-content:center;border:2px solid {tc}">{initials}</div>'
        )
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:{tc};color:white;font-weight:bold;font-size:{size//4}px;'
        f'display:flex;align-items:center;justify-content:center;'
        f'border:2px solid {tc};flex-shrink:0">{initials}</div>'
    )


def ranking_block_html(rows: list[dict], stat_col: str, stat_label: str, unit: str,
                        negative: bool, team_color: str, league_mean: float) -> str:
    """
    Génère un bloc de classement style LNR :
    rang · photo · nom + poste · valeur stat
    """
    tc_r = int(team_color[1:3], 16)
    tc_g = int(team_color[3:5], 16)
    tc_b = int(team_color[5:7], 16)

    html = f"""
    <div style="background:#111827;border-radius:12px;overflow:hidden;margin-bottom:8px">
      <div style="padding:10px 16px;background:rgba({tc_r},{tc_g},{tc_b},0.15);
                  border-bottom:1px solid rgba({tc_r},{tc_g},{tc_b},0.3);
                  display:flex;align-items:center;justify-content:space-between">
        <span style="font-weight:700;font-size:0.95em;color:#F9FAFB">{stat_label}</span>
        <span style="font-size:0.75em;color:#9CA3AF">Moy. Top14 : {league_mean:.1f} {unit}</span>
      </div>
    """

    for i, row in enumerate(rows):
        name = row.get("name", "")
        pos = row.get("position_label", row.get("position_group", ""))
        val = row.get(stat_col)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        val = float(val)

        # Barre de progression relative au max
        max_val = float(rows[0].get(stat_col, 1)) if rows else 1
        pct = min(100, int(val / max_val * 100)) if max_val > 0 else 0

        photo = player_photo_html(row, size=44)
        rank_color = ("#FFD700" if i == 0 else ("#C0C0C0" if i == 1 else ("#CD7F32" if i == 2 else "#6B7280")))
        vs_league = val - league_mean
        vs_str = f"+{vs_league:.1f}" if vs_league >= 0 else f"{vs_league:.1f}"
        vs_color = "#10B981" if vs_league >= 0 else "#EF4444"

        html += f"""
      <div style="display:flex;align-items:center;gap:12px;padding:10px 16px;
                  border-bottom:1px solid #1F2937;
                  background:{'rgba(' + str(tc_r) + ',' + str(tc_g) + ',' + str(tc_b) + ',0.08)' if i == 0 else 'transparent'}">
        <div style="width:24px;text-align:center;font-weight:700;font-size:0.95em;color:{rank_color};flex-shrink:0">
          {i+1}
        </div>
        <div style="flex-shrink:0">{photo}</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:0.9em;color:#F9FAFB;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
          <div style="font-size:0.75em;color:#9CA3AF">{pos}</div>
          <div style="margin-top:4px;height:3px;background:#374151;border-radius:2px">
            <div style="width:{pct}%;height:3px;background:{team_color};border-radius:2px"></div>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:1.2em;font-weight:700;color:#F9FAFB">{val:.1f}</div>
          <div style="font-size:0.7em;color:{vs_color}">{vs_str} vs Top14</div>
        </div>
      </div>
        """

    html += "</div>"
    return html


# ─────────────────────────────────────────────
# Header — sélecteur équipe
# ─────────────────────────────────────────────
teams = sorted(df["team"].unique().tolist())

col_sel, _ = st.columns([2, 5])
with col_sel:
    selected_team = st.selectbox("Equipe", teams, label_visibility="collapsed")

team_color = TEAM_COLORS.get(selected_team, "#EF4444")
tc_r = int(team_color[1:3], 16)
tc_g = int(team_color[3:5], 16)
tc_b = int(team_color[5:7], 16)

team_df = df[df["team"] == selected_team].copy()

# KPIs
ts_row = ts[ts["team"] == selected_team]
team_score = float(ts_row["team_rating"].values[0]) if not ts_row.empty else 0.0
all_scores = ts["team_rating"].sort_values(ascending=False).tolist()
rank_ts = all_scores.index(team_score) + 1 if team_score in all_scores else "?"

avg_rating = team_df["rating"].mean()
n_players = len(team_df)
n_intl = team_df[team_df["nationality"] != "France"].shape[0] if "nationality" in team_df.columns else 0

# Logo club depuis CDN LNR
team_slug_map = {
    "Toulouse": "toulouse", "Bordeaux": "union-bordeaux-begles",
    "Lyon": "lou-rugby", "La Rochelle": "stade-rochelais",
    "Racing 92": "racing-92", "Clermont": "asm-clermont",
    "Montpellier": "montpellier-hrault-rugby", "Toulon": "rc-toulon",
    "Paris": "stade-francais-paris", "Castres": "castres-olympique",
    "Pau": "section-paloise", "Bayonne": "aviron-bayonnais",
    "Perpignan": "usa-perpignan", "Montauban": "us-montauban",
}
club_slug = team_slug_map.get(selected_team, selected_team.lower().replace(" ", "-"))
club_logo_url = f"https://cdn.lnr.fr/club/{club_slug}/photo/logo.{LNR_PHOTO_HASH}"

# Header HTML style LNR
st.markdown(
    f"""
    <div style="background:linear-gradient(135deg,rgba({tc_r},{tc_g},{tc_b},0.25),rgba({tc_r},{tc_g},{tc_b},0.05));
                border-left:5px solid {team_color};border-radius:12px;
                padding:20px 24px;margin-bottom:20px;
                display:flex;align-items:center;gap:20px">
      <img src="{club_logo_url}" style="height:72px;width:72px;object-fit:contain"
           onerror="this.style.display='none'">
      <div>
        <h2 style="margin:0;font-size:2em;color:#F9FAFB">{selected_team}</h2>
        <p style="margin:4px 0 0;color:#9CA3AF">Top 14 · Saison 2025–2026 · #{rank_ts}/14</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Team Strength", f"{team_score:.1f}", f"#{rank_ts}/14")
k2.metric("Note moyenne", f"{avg_rating:.1f}")
k3.metric("Effectif tracké", f"{n_players}")
k4.metric("Internationaux", f"{n_intl}")
if "starter_rate" in team_df.columns:
    k5.metric("Taux titulaire méd.", f"{team_df['starter_rate'].median():.0%}")

st.divider()

# ─────────────────────────────────────────────
# Onglets
# ─────────────────────────────────────────────
tab_rank, tab_form, tab_profil, tab_effectif = st.tabs([
    "📊 Meilleurs joueurs",
    "🔥 Forme récente",
    "🕸️ Profil d'équipe",
    "👥 Effectif complet",
])


# ══════════════════════════════════════════════
# TAB 1 — RANKINGS STYLE LNR avec photos
# ══════════════════════════════════════════════
with tab_rank:
    st.caption("Stats /80 min · saison complète · min. 2 matchs joués")

    RANKING_STATS = [
        ("tackles_per80",       "Plaquages",          "/80",  False),
        ("line_breaks_per80",   "Franchissements",    "/80",  False),
        ("offloads_per80",      "Offloads",           "/80",  False),
        ("turnovers_won_per80", "Turnovers gagnés",   "/80",  False),
        ("points_scored_per80", "Points marqués",     "/80",  False),
        ("penalties_per80",     "Pénalités",          "/80",  True),
    ]

    valid_base = team_df[team_df["matches_played"].fillna(0) >= 2].copy()

    # 2 colonnes × N rangées
    col_l, col_r = st.columns(2, gap="large")
    columns_cycle = [col_l, col_r]

    for idx, (stat_col, stat_label, unit, negative) in enumerate(RANKING_STATS):
        target_col = columns_cycle[idx % 2]

        valid = valid_base.dropna(subset=[stat_col])
        if valid.empty:
            continue
        ranked = valid.sort_values(stat_col, ascending=negative).head(8)
        league_mean = df.dropna(subset=[stat_col])[stat_col].mean()

        rows = ranked.to_dict("records")
        block = ranking_block_html(rows, stat_col, stat_label, unit, negative, team_color, league_mean)

        with target_col:
            st.markdown(block, unsafe_allow_html=True)

    st.divider()

    # Top 10 par note globale — avec photos
    st.markdown("#### Meilleurs joueurs — Note globale")
    top10 = team_df.sort_values("rating", ascending=False).head(10).to_dict("records")

    top10_html = '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px">'
    for rank, p in enumerate(top10):
        url = get_photo_url(p)
        tier = rating_to_tier(p["rating"])
        tcolor = TIER_COLORS[tier]
        name = p.get("name", "")
        pos = p.get("position_label", p.get("position_group", ""))
        rating = p["rating"]
        photo_src = url or ""
        initials = "".join(w[0].upper() for w in name.split()[:2] if w)

        top10_html += f"""
        <div style="background:#111827;border-radius:10px;padding:14px;width:calc(20% - 12px);
                    min-width:130px;text-align:center;border:1px solid rgba({tc_r},{tc_g},{tc_b},0.3);
                    position:relative">
          <div style="position:absolute;top:8px;left:8px;font-size:0.7em;color:#9CA3AF;font-weight:700">
            #{rank+1}
          </div>
          <div style="margin:0 auto 8px;width:56px;height:56px;border-radius:50%;overflow:hidden;
                      border:2px solid {tcolor};background:#1F2937">
        """
        if photo_src:
            top10_html += (
                f'<img src="{photo_src}" style="width:100%;height:100%;object-fit:cover" '
                f'onerror="this.outerHTML=\'<div style=&quot;width:100%;height:100%;'
                f'display:flex;align-items:center;justify-content:center;'
                f'font-weight:bold;color:white;font-size:16px&quot;>{initials}</div>\'">'
            )
        else:
            top10_html += (
                f'<div style="width:100%;height:100%;display:flex;align-items:center;'
                f'justify-content:center;font-weight:bold;color:white;font-size:16px">{initials}</div>'
            )
        top10_html += f"""
          </div>
          <div style="font-weight:600;font-size:0.82em;color:#F9FAFB;margin-bottom:2px;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="{name}">{name}</div>
          <div style="font-size:0.7em;color:#9CA3AF;margin-bottom:6px">{pos}</div>
          <div style="display:inline-block;padding:2px 10px;border-radius:20px;
                      background:{tcolor}22;border:1px solid {tcolor};
                      font-weight:700;color:{tcolor};font-size:1em">{rating:.1f}</div>
        </div>
        """
    top10_html += "</div>"
    st.markdown(top10_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════
# TAB 2 — FORME RÉCENTE avec photos
# ══════════════════════════════════════════════
with tab_form:
    has_form = "form_tackles_per80" in team_df.columns and team_df["form_tackles_per80"].notna().any()

    if not has_form:
        st.warning("Données de forme non disponibles — relancer `compute_form.py`.")
    else:
        st.caption("Rolling **5 derniers matchs** — feuilles de match LNR")

        # ---- Top 5 forme par stat ----
        form_stats_def = [
            ("form_tackles_per80",    "tackles_per80",    "Plaquages forme"),
            ("form_line_breaks_per80","line_breaks_per80","Franchissements forme"),
            ("form_offloads_per80",   "offloads_per80",   "Offloads forme"),
            ("form_turnovers_per80",  "turnovers_won_per80","Turnovers forme"),
        ]

        valid_form = team_df[team_df["form_window"].fillna(0) >= 3].copy()

        fc1, fc2 = st.columns(2, gap="large")
        for fi, (form_col, season_col, label) in enumerate(form_stats_def):
            target = fc1 if fi % 2 == 0 else fc2
            fvalid = valid_form.dropna(subset=[form_col])
            if fvalid.empty:
                continue
            ranked = fvalid.sort_values(form_col, ascending=False).head(8)
            league_mean_form = df.dropna(subset=[season_col])[season_col].mean()
            rows = ranked.rename(columns={form_col: "__form_val__"}).to_dict("records")
            # patch stat_col name back for ranking_block_html
            for r in rows:
                r[form_col] = r.pop("__form_val__", r.get(form_col))

            block = ranking_block_html(ranked.to_dict("records"), form_col, label, "/80", False, team_color, league_mean_form)
            with target:
                st.markdown(block, unsafe_allow_html=True)

        st.divider()

        # ---- Joueurs en montée / baisse ----
        st.markdown("#### Tendances de forme (plaquages)")
        valid_delta = valid_form.dropna(subset=["form_tackles_per80", "tackles_per80"]).copy()
        valid_delta["delta"] = valid_delta["form_tackles_per80"] - valid_delta["tackles_per80"]

        col_up, col_dn = st.columns(2, gap="large")

        def trend_row_html(p: dict, delta: float, color: str, arrow: str) -> str:
            photo = player_photo_html(p, 40)
            name = p.get("name", "")
            pos = p.get("position_label", p.get("position_group", ""))
            season_val = p.get("tackles_per80", 0) or 0
            form_val = p.get("form_tackles_per80", 0) or 0
            return f"""
            <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                        border-radius:8px;background:#111827;margin-bottom:6px">
              {photo}
              <div style="flex:1;min-width:0">
                <div style="font-weight:600;font-size:0.88em;color:#F9FAFB;
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
                <div style="font-size:0.72em;color:#9CA3AF">{pos}</div>
              </div>
              <div style="text-align:right;flex-shrink:0">
                <div style="font-size:0.72em;color:#9CA3AF">saison: {season_val:.1f} → form: {form_val:.1f}</div>
                <div style="font-weight:700;color:{color};font-size:1em">{arrow} {abs(delta):.1f}</div>
              </div>
            </div>
            """

        with col_up:
            st.markdown(f"<p style='color:#10B981;font-weight:700;margin-bottom:8px'>▲ En montée</p>", unsafe_allow_html=True)
            for _, row in valid_delta.nlargest(5, "delta").iterrows():
                st.markdown(trend_row_html(row.to_dict(), row["delta"], "#10B981", "▲"), unsafe_allow_html=True)

        with col_dn:
            st.markdown(f"<p style='color:#EF4444;font-weight:700;margin-bottom:8px'>▼ En baisse</p>", unsafe_allow_html=True)
            for _, row in valid_delta.nsmallest(5, "delta").iterrows():
                st.markdown(trend_row_html(row.to_dict(), row["delta"], "#EF4444", "▼"), unsafe_allow_html=True)

        st.divider()

        # Heatmap
        st.markdown("#### Heatmap forme vs saison (z-score)")
        hm_cols = ["form_tackles_per80","form_line_breaks_per80","form_offloads_per80","form_turnovers_per80"]
        s_cols  = ["tackles_per80","line_breaks_per80","offloads_per80","turnovers_won_per80"]
        labels  = ["Plaquages","Franch.","Offloads","TO"]

        hm_df = valid_form.dropna(subset=["form_tackles_per80"]).copy()
        if not hm_df.empty:
            delta_data = {}
            for fc, sc, lbl in zip(hm_cols, s_cols, labels):
                if fc in hm_df.columns and sc in hm_df.columns:
                    d = hm_df[fc].fillna(0) - hm_df[sc].fillna(0)
                    std = df[sc].std()
                    delta_data[lbl] = (d / std if std > 0 else d).values
            if delta_data:
                dm = pd.DataFrame(delta_data, index=hm_df["name"].values)
                dm = dm.sort_values("Plaquages", ascending=False)
                fig_hm = px.imshow(
                    dm.T, color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                    aspect="auto", labels=dict(color="Δ (σ)"),
                )
                fig_hm.update_layout(
                    height=max(180, 40 * len(labels) + 80),
                    margin=dict(l=10,r=10,t=20,b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(tickfont=dict(size=9)),
                )
                st.plotly_chart(fig_hm, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 3 — PROFIL D'ÉQUIPE
# ══════════════════════════════════════════════
with tab_profil:
    col_radar, col_kpis = st.columns([3, 2])

    with col_radar:
        st.markdown("**Radar — profil vs moyenne Top 14**")
        axes_team = {k: float(team_df[f"axis_{k.lower()}"].mean()) for k in ["att","def","disc","ctrl","kick","pow"]}
        axes_league = {k: float(df[f"axis_{k.lower()}"].mean()) for k in ["att","def","disc","ctrl","kick","pow"]}
        ks = ["ATT","DEF","DISC","CTRL","KICK","POW"]
        ks_c = ks + [ks[0]]

        fig_radar = go.Figure()
        vs_team = [axes_team[k.lower()] for k in ks]
        fig_radar.add_trace(go.Scatterpolar(
            r=vs_team + [vs_team[0]], theta=ks_c, fill="toself", name=selected_team,
            line=dict(color=team_color, width=2.5),
            fillcolor=f"rgba({tc_r},{tc_g},{tc_b},0.2)",
        ))
        vs_lg = [axes_league[k.lower()] for k in ks]
        fig_radar.add_trace(go.Scatterpolar(
            r=vs_lg + [vs_lg[0]], theta=ks_c, name="Moy. Top 14",
            line=dict(color="#6B7280", width=1.5, dash="dot"), fill="none",
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[30,75], tickfont=dict(size=8))),
            legend=dict(x=0.5, y=-0.12, xanchor="center", orientation="h"),
            margin=dict(l=10,r=10,t=20,b=60), height=380, paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with col_kpis:
        st.markdown("**Indices vs Top 14**")
        for k, label, icon in [
            ("att","Ball Carry","⚡"),("def","Défense","🛡️"),("disc","Discipline","📋"),
            ("ctrl","Breakdown","🔄"),("kick","Jeu au pied","👟"),("pow","Puissance","💪"),
        ]:
            tv = float(team_df[f"axis_{k}"].mean())
            lv = float(df[f"axis_{k}"].mean())
            st.metric(f"{icon} {label}", f"{tv:.1f}", f"{tv-lv:+.1f} vs Top14")

    st.divider()

    # Scatter top14
    st.markdown("**Positionnement — toutes équipes**")
    team_summary = df.groupby("team").agg(
        rating=("rating","mean"), axis_att=("axis_att","mean"),
        axis_def=("axis_def","mean"), axis_kick=("axis_kick","mean"),
    ).reset_index().round(1)

    ax_x = st.selectbox("Axe X", ["axis_att","axis_def","rating","axis_kick"], index=0,
                         format_func=lambda x: {"rating":"Note","axis_att":"ATT","axis_def":"DEF","axis_kick":"KICK"}[x])
    ax_y = st.selectbox("Axe Y", ["axis_def","axis_att","rating","axis_kick"], index=0,
                         format_func=lambda x: {"rating":"Note","axis_att":"ATT","axis_def":"DEF","axis_kick":"KICK"}[x])

    fig_sc = go.Figure()
    for _, row in team_summary.iterrows():
        is_sel = row["team"] == selected_team
        tc2 = TEAM_COLORS.get(row["team"], "#374151")
        fig_sc.add_trace(go.Scatter(
            x=[row[ax_x]], y=[row[ax_y]], mode="markers+text", showlegend=False,
            text=[row["team"]], textposition="top center",
            marker=dict(size=16 if is_sel else 10, color=team_color if is_sel else tc2,
                        line=dict(color="white" if is_sel else tc2, width=2 if is_sel else 1)),
            textfont=dict(size=12 if is_sel else 9, color=team_color if is_sel else "#9CA3AF"),
        ))
    fig_sc.update_layout(
        xaxis_title={"rating":"Note","axis_att":"ATT","axis_def":"DEF","axis_kick":"KICK"}[ax_x],
        yaxis_title={"rating":"Note","axis_att":"ATT","axis_def":"DEF","axis_kick":"KICK"}[ax_y],
        height=380, margin=dict(l=10,r=10,t=20,b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    fig_sc.update_xaxes(gridcolor="#1F2937"); fig_sc.update_yaxes(gridcolor="#1F2937")
    st.plotly_chart(fig_sc, use_container_width=True)

    st.divider()
    st.markdown("**Distribution des notes par poste**")
    pos_fig = px.box(
        team_df.dropna(subset=["rating"]), x="position_label", y="rating",
        color="position_group", points="all", hover_data=["name"],
        labels={"position_label":"Poste","rating":"Note","position_group":"Groupe"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    pos_fig.update_layout(
        height=320, margin=dict(l=10,r=10,t=10,b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    pos_fig.update_xaxes(gridcolor="#1F2937"); pos_fig.update_yaxes(gridcolor="#1F2937")
    st.plotly_chart(pos_fig, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 4 — EFFECTIF COMPLET avec photos
# ══════════════════════════════════════════════
with tab_effectif:
    st.caption("Tous les joueurs trackés · cliquer sur une ligne pour voir la fiche")

    cf1, cf2 = st.columns(2)
    with cf1:
        pos_filter = st.multiselect("Poste", sorted(team_df["position_group"].dropna().unique().tolist()))
    with cf2:
        min_matches = st.slider("Matchs min.", 0, 18, 1)

    eff = team_df.copy()
    if pos_filter:
        eff = eff[eff["position_group"].isin(pos_filter)]
    eff = eff[eff["matches_played"].fillna(0) >= min_matches]
    eff = eff.sort_values("rating", ascending=False)

    # Affichage avec photo en HTML — style LNR effectif
    for _, p in eff.iterrows():
        pdict = p.to_dict()
        photo = player_photo_html(pdict, 50)
        tier = rating_to_tier(p["rating"])
        tcolor = TIER_COLORS[tier]
        pos = p.get("position_label", p.get("position_group", ""))
        age = int(p.get("age", 0) or 0)
        mp = int(p.get("matches_played", 0) or 0)
        nat = p.get("nationality", "")
        tackles = p.get("tackles_per80")
        form_t = p.get("form_tackles_per80")
        sr = p.get("starter_rate")
        sr_str = f"{sr:.0%}" if sr and not pd.isna(sr) else "–"
        form_str = f"{form_t:.1f}" if form_t and not pd.isna(form_t) else "–"
        tackles_str = f"{tackles:.1f}" if tackles and not pd.isna(tackles) else "–"
        conf_badge = p.get("confidence_badge", "")
        conf = int(p.get("confidence_score", 50) or 50)
        conf_color = "#10B981" if conf >= 70 else ("#F59E0B" if conf >= 40 else "#EF4444")

        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:14px;padding:10px 16px;
                        background:#111827;border-radius:10px;margin-bottom:6px;
                        border:1px solid rgba({tc_r},{tc_g},{tc_b},0.15)">
              {photo}
              <div style="flex:1;min-width:0">
                <div style="font-weight:700;font-size:0.95em;color:#F9FAFB">{p['name']}</div>
                <div style="font-size:0.78em;color:#9CA3AF">{pos} · {nat} · {age} ans</div>
              </div>
              <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
                <div style="text-align:center">
                  <div style="font-size:0.65em;color:#9CA3AF;text-transform:uppercase">Matchs</div>
                  <div style="font-weight:600;color:#F9FAFB">{mp}</div>
                </div>
                <div style="text-align:center">
                  <div style="font-size:0.65em;color:#9CA3AF;text-transform:uppercase">Plq/80</div>
                  <div style="font-weight:600;color:#F9FAFB">{tackles_str}</div>
                </div>
                <div style="text-align:center">
                  <div style="font-size:0.65em;color:#9CA3AF;text-transform:uppercase">Forme</div>
                  <div style="font-weight:600;color:#3B82F6">{form_str}</div>
                </div>
                <div style="text-align:center">
                  <div style="font-size:0.65em;color:#9CA3AF;text-transform:uppercase">Tit.%</div>
                  <div style="font-weight:600;color:#F9FAFB">{sr_str}</div>
                </div>
                <div style="text-align:center;min-width:56px">
                  <div style="font-size:0.65em;color:#9CA3AF;text-transform:uppercase">Note</div>
                  <div style="font-weight:800;font-size:1.15em;color:{tcolor}">{p['rating']:.1f}</div>
                </div>
                <div style="text-align:center">
                  <div style="font-size:0.65em;color:#9CA3AF;text-transform:uppercase">Conf.</div>
                  <div style="font-size:0.78em;color:{conf_color};font-weight:600">{conf_badge}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(f"{len(eff)} joueurs · Forme = plaquages /80 sur les 5 derniers matchs")
