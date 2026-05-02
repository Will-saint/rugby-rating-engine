"""
Page 1 — Cartes joueur style FIFA
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from utils import load_data, page_config, AXIS_LABELS, AXIS_COLORS, rating_to_tier, TIER_COLORS, AXIS_DESCRIPTIONS, get_available_positions, get_photo_url, fetch_player_photo_bytes, season_selector, nat_flag, ALL_SEASONS_PATH
from engine.card import render_card
from engine.ratings import get_rating_breakdown

page_config("Cartes Joueurs")

st.title("Cartes Joueurs")
st.markdown("Sélectionne un joueur pour voir sa carte FIFA-style et ses statistiques détaillées.")

season = season_selector("_pc")
df = load_data(season)

# --- Filtres ---
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    teams = ["Toutes"] + sorted(df["team"].unique().tolist())
    selected_team = st.selectbox("Equipe", teams)
with col_f2:
    positions = ["Tous"] + get_available_positions(df)
    selected_pos = st.selectbox("Poste", positions)
with col_f3:
    search = st.text_input("Rechercher un joueur", placeholder="Ex: Dupont...")

filtered = df.copy()
if selected_team != "Toutes":
    filtered = filtered[filtered["team"] == selected_team]
if selected_pos != "Tous":
    filtered = filtered[filtered["position_group"] == selected_pos]
if search:
    filtered = filtered[filtered["name"].str.contains(search, case=False, na=False)]

filtered = filtered.sort_values("rating", ascending=False)

if filtered.empty:
    st.warning("Aucun joueur trouvé avec ces filtres.")
    st.stop()

player_names = filtered["name"].tolist()
selected_name = st.selectbox("Joueur", player_names, format_func=lambda n: n)

player_row = filtered[filtered["name"] == selected_name].iloc[0]
player = player_row.to_dict()

st.divider()

# --- Photo LNR (header banner) ---
photo_url = get_photo_url(player)
photo_bytes = fetch_player_photo_bytes(photo_url) if photo_url else None

tier = rating_to_tier(player["rating"])
tier_color = TIER_COLORS[tier]

def _safe_str(v) -> str:
    """Convertit une valeur en str, retourne '' si NaN/None."""
    if v is None:
        return ""
    try:
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    return str(v)

def _safe_int(v, default: int = 0) -> int:
    """Convertit une valeur en int, retourne default si NaN/None."""
    try:
        f = float(v)
        if math.isnan(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default

flag = nat_flag(_safe_str(player.get("nationality", "")))
_form_badge = ""
_ft_raw = _safe_str(player.get("form_trend", ""))
if _ft_raw and _ft_raw[0] in ("↗", "↘", "→"):
    _fc = {"↗": "#10B981", "↘": "#EF4444", "→": "#9CA3AF"}[_ft_raw[0]]
    _fl = {"↗": "En forme", "↘": "En difficulté", "→": "Neutre"}[_ft_raw[0]]
    _form_badge = (
        f'<span style="background:{_fc}22;border:1px solid {_fc};border-radius:6px;'
        f'padding:2px 10px;font-size:0.8em;color:{_fc};margin-left:10px">'
        f'{_ft_raw[0]} {_fl}</span>'
    )
_age_badge = ""
_age_factor_val = player.get("age_factor", 0.0)
try:
    _af = float(_age_factor_val) if _age_factor_val is not None else 0.0
    if math.isnan(_af):
        _af = 0.0
except (TypeError, ValueError):
    _af = 0.0
if abs(_af) >= 0.1:
    _age_sign  = "+" if _af > 0 else ""
    _age_label = "Prime" if _af >= 2.5 else ("En forme" if _af >= 1.0 else ("Montée" if _af >= 0 else ("Vétéran" if _af >= -0.5 else "Post-prime")))
    _age_bg    = "#10B98122" if _af > 0 else "#EF444422"
    _age_border= "#10B981"   if _af > 0 else "#EF4444"
    _age_color = "#10B981"   if _af > 0 else "#EF4444"
    _age_badge = (
        f'<span style="background:{_age_bg};border:1px solid {_age_border};border-radius:6px;'
        f'padding:2px 10px;font-size:0.8em;color:{_age_color};margin-left:8px">'
        f'🎂 {_safe_int(player.get("age"))} ans · {_age_label} ({_age_sign}{_af:.1f} pts)</span>'
    )

_intl_badge = ""
_team_intl_str = _safe_str(player.get("team_intl", ""))
if _team_intl_str:
    _intl_badge = (
        f'<span style="background:#3B82F622;border:1px solid #3B82F6;border-radius:6px;'
        f'padding:2px 10px;font-size:0.8em;color:#60A5FA;margin-left:8px">'
        f'🌍 {_team_intl_str}</span>'
    )

# 1. Tier badge avec couleurs spécifiques
_TIER_BADGE_COLORS = {
    "LEGENDAIRE": "#FFD700", "OR": "#C8A840",
    "ARGENT": "#94A3B8",    "BRONZE": "#CD7F32", "STANDARD": "#6B7280",
}
_tier_badge_color = _TIER_BADGE_COLORS.get(tier, "#6B7280")
_tier_badge_html = (
    f'<span style="background:{_tier_badge_color}22;border:1px solid {_tier_badge_color};'
    f'border-radius:6px;padding:3px 12px;font-size:0.8em;font-weight:700;'
    f'color:{_tier_badge_color};letter-spacing:0.05em">{tier}</span>'
)

# 2. Confiance visuelle avec dots
_conf_raw = player.get("confidence", player.get("confidence_score", 0.5))
try:
    _conf_f = float(_conf_raw) if _conf_raw is not None else 0.5
    if math.isnan(_conf_f):
        _conf_f = 0.5
    if _conf_f > 1.0:
        _conf_f /= 100.0
except (TypeError, ValueError):
    _conf_f = 0.5
if _conf_f >= 0.9:
    _conf_dots, _conf_dot_color = "&#9679;&#9679;&#9679; Haute", "#10B981"
elif _conf_f >= 0.7:
    _conf_dots, _conf_dot_color = "&#9679;&#9679;&#9675; Moyenne", "#F59E0B"
else:
    _conf_dots, _conf_dot_color = "&#9679;&#9675;&#9675; Basse", "#EF4444"
_conf_badge_html = (
    f'<span style="background:{_conf_dot_color}18;border:1px solid {_conf_dot_color}44;'
    f'border-radius:6px;padding:3px 10px;font-size:0.78em;color:{_conf_dot_color};margin-left:8px">'
    f'{_conf_dots}</span>'
)

# 3. Ligne internationale si disponible
_banner_intl_line = ""
_ri_raw = player.get("rating_intl")
_mi_raw = player.get("matches_intl", 0)
try:
    _ri_f = float(_ri_raw) if _ri_raw not in (None, "", "nan") else None
    if _ri_f is not None and not math.isnan(_ri_f):
        _mi_int = _safe_int(_mi_raw)
        _banner_intl_line = (
            f'<div style="color:#60A5FA;font-size:0.8em;margin-top:5px">'
            f'🌍 {_mi_int} sélections &nbsp;·&nbsp; Note Naim : '
            f'<b style="color:#93C5FD">{_ri_f:.1f}</b></div>'
        )
except (TypeError, ValueError):
    pass

# Banner header (with or without photo)
_banner_photo_html = ""
if photo_bytes:
    import base64 as _b64
    _photo_b64 = _b64.b64encode(photo_bytes).decode()
    _banner_photo_html = (
        f'<img src="data:image/jpeg;base64,{_photo_b64}" '
        f'style="height:120px;width:auto;border-radius:8px;'
        f'border:2px solid {tier_color}88;object-fit:cover;flex-shrink:0"/>'
    )

st.markdown(
    f"""<div style="
        background:linear-gradient(135deg,{tier_color}18 0%,{tier_color}06 60%,#080D1A 100%);
        border:1px solid {tier_color}44;border-left:4px solid {tier_color};
        border-radius:14px;padding:22px 28px;margin-bottom:16px;
        display:flex;align-items:center;gap:24px;
    ">
      {_banner_photo_html}
      <div style="flex:1;min-width:0">
        <div style="color:{tier_color};font-size:0.75em;font-weight:600;
                    letter-spacing:0.15em;text-transform:uppercase;margin-bottom:4px">
          {player.get('position_label', player['position_group'])} · {player['team']}
        </div>
        <div style="font-family:'Rajdhani',sans-serif;font-weight:700;font-size:2.2em;
                    color:#F1F5F9;line-height:1.1;margin-bottom:6px">
          {flag} {player['name']} {_form_badge} {_age_badge} {_intl_badge}
        </div>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px">
          <div style="background:{tier_color}22;border:1px solid {tier_color};
                      border-radius:8px;padding:6px 20px;display:inline-block">
            <span style="font-family:'Rajdhani',sans-serif;font-size:2em;font-weight:700;
                         color:{tier_color}">{player['rating']:.1f}</span>
          </div>
          {_tier_badge_html}
          {_conf_badge_html}
        </div>
        <div style="color:#9CA3AF;font-size:0.82em;line-height:1.6">
          {_safe_int(player.get('age'))} ans &nbsp;·&nbsp;
          {_safe_int(player.get('height_cm'))} cm &nbsp;·&nbsp;
          {_safe_int(player.get('weight_kg'))} kg &nbsp;·&nbsp;
          {_safe_int(player.get('matches_played'))} matchs
        </div>
        {_banner_intl_line}
      </div>
    </div>""",
    unsafe_allow_html=True,
)

# --- Layout carte FIFA + détails ---
col_card, col_details = st.columns([1, 2], gap="large")

with col_card:
    card_bytes = render_card(player)
    st.image(card_bytes, use_container_width=True)

    st.download_button(
        "Télécharger la carte (PNG)",
        data=card_bytes,
        file_name=f"carte_{selected_name.replace(' ', '_')}.png",
        mime="image/png",
        use_container_width=True,
    )
    # Fiche scouting complète (PDF/PNG haute résolution)
    try:
        from engine.scouting_card import generate_scouting_card
        if st.button("Générer fiche scouting", use_container_width=True,
                     help="Fiche complète : radar, forme, stats, données intl"):
            with st.spinner("Génération..."):
                scout_bytes = generate_scouting_card(player, df)
            st.download_button(
                "Télécharger la fiche scouting (PNG)",
                data=scout_bytes,
                file_name=f"scouting_{selected_name.replace(' ', '_')}.png",
                mime="image/png",
                use_container_width=True,
            )
    except Exception as _e:
        st.caption(f"Fiche scouting indisponible : {_e}")

with col_details:
    _nat_val = _safe_str(player.get("nationality", "")) or "?"
    _mp_val  = str(_safe_int(player.get("matches_played")))
    _min_avg = player.get("minutes_avg", 0)
    try:
        _min_val = f"{float(_min_avg):.0f}" if _min_avg and not math.isnan(float(_min_avg)) else "—"
    except (TypeError, ValueError):
        _min_val = "—"
    _conf_val = _safe_str(player.get("confidence_badge", "")) or "—"
    _stat_items = [
        ("Nationalité", _nat_val, "#F97316"),
        ("Matchs joués", _mp_val, "#3B82F6"),
        ("Min. moyennes", _min_val, "#8B5CF6"),
        ("Confiance", _conf_val, "#10B981"),
    ]
    _si_cols = st.columns(4)
    for _sic, (_slabel, _sval, _scolor) in zip(_si_cols, _stat_items):
        with _sic:
            st.markdown(
                f"""<div style="
                    background:{_scolor}12;border:1px solid {_scolor}33;
                    border-radius:10px;padding:10px 12px;text-align:center;
                ">
                  <div style="color:#9CA3AF;font-size:0.7em;text-transform:uppercase;
                              letter-spacing:0.06em;margin-bottom:3px">{_slabel}</div>
                  <div style="font-family:'Rajdhani',sans-serif;font-weight:700;
                              font-size:1.25em;color:{_scolor}">{_sval}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # Confidence badge + rank intra-poste
    conf_badge = _safe_str(player.get("confidence_badge", ""))
    conf = _safe_int(player.get("confidence_score"), 50)
    conf_color = "#10B981" if conf >= 70 else ("#F59E0B" if conf >= 40 else "#EF4444")
    rank_pos = player.get("rank_position", "?")
    pct_pos = player.get("rating_percentile_position")
    pct_str = f"{pct_pos:.0f}e pc." if isinstance(pct_pos, (int, float)) else "?"
    rating_raw_val = player.get("rating_raw", player.get("rating", 0))
    badge_html = (
        f'&nbsp;<span style="background:{conf_color}22;border:1px solid {conf_color};'
        f'padding:1px 8px;border-radius:4px;font-size:0.8em;color:{conf_color}">'
        f'Confiance {conf_badge}</span>'
    ) if conf_badge else ""

    # DATA_INSUFFICIENT badge
    data_insuf = bool(player.get("data_insufficient", False))
    mp = int(player.get("matches_played", 0) or 0)
    insuf_html = ""
    if data_insuf:
        insuf_html = (
            f'&nbsp;<span style="background:#7F1D1D;border:1px solid #EF4444;'
            f'padding:2px 10px;border-radius:4px;font-size:0.8em;color:#FCA5A5;font-weight:bold">'
            f'⚠ DONNÉES INSUFFISANTES ({mp} matchs, conf {conf}%)</span>'
        )

    st.markdown(
        f'<div style="display:flex;gap:16px;margin:4px 0 10px;flex-wrap:wrap;align-items:center">'
        f'<span style="font-size:0.85em"><b style="color:{conf_color}">{conf}%</b>{badge_html}</span>'
        f'<span style="font-size:0.85em;color:#9CA3AF">Rang {player["position_group"]} : '
        f'<b style="color:#E5E7EB">#{rank_pos}</b> ({pct_str})</span>'
        f'<span style="font-size:0.85em;color:#9CA3AF">Brute : '
        f'<b style="color:#E5E7EB">{float(rating_raw_val):.1f}</b></span>'
        f'{insuf_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
    if data_insuf:
        st.warning(
            f"**Note peu fiable** — {mp} matchs Top14 joués et/ou confiance {conf}%. "
            "Ce joueur est probablement en sélection nationale ou blessé. "
            "La note ne reflète pas son niveau réel."
        )

    with st.expander("Comprendre les 6 axes"):
        for ax_key, ax_info in AXIS_DESCRIPTIONS.items():
            st.markdown(f"**{ax_info['emoji']} {ax_info['label']}** — {', '.join(ax_info['metrics'])}")
            st.caption(ax_info["note"])

    t14_axes  = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow", "axis_gabarit", "axis_consistency"]
    t14_labels = [AXIS_LABELS[a] for a in t14_axes]
    intl_axes  = ["axis_course_intl","axis_distrib_intl","axis_kicking_intl",
                  "axis_physique_intl","axis_rigueur_intl","axis_danger_intl","axis_melee_intl"]
    intl_labels = ["Course","Distrib","Kicking","Physique","Rigueur","Danger","Mêlée"]

    has_intl_data = any(
        player.get(a) not in (None, "") and str(player.get(a)) != "nan"
        for a in intl_axes
    )

    if has_intl_data:
        st.markdown("**Radar — Top14 vs International**")
        rad_col1, rad_col2 = st.columns(2)

        def _make_radar(vals, labels, color, title, note):
            closed = vals + [vals[0]]
            cl = labels + [labels[0]]
            fig = go.Figure(go.Scatterpolar(
                r=closed, theta=cl, fill="toself",
                fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.25)",
                line=dict(color=color, width=2), name=title,
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0,100], tickfont=dict(size=8))),
                showlegend=False, title=dict(text=title, font=dict(size=12), x=0.5),
                margin=dict(l=30,r=30,t=40,b=10), height=280,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            return fig

        with rad_col1:
            vals_t14 = [float(player.get(a, 50)) for a in t14_axes]
            st.plotly_chart(_make_radar(vals_t14, t14_labels, "#EF4444", "Top14 Saison", ""), use_container_width=True)
            ri = player.get("rating_intl")
            st.caption(f"Note T14 : **{player['rating']:.1f}**")

        with rad_col2:
            vals_intl = [float(v) if (v := player.get(a)) not in (None,"") and str(v) != "nan" else 50
                         for a in intl_axes]
            team_intl = player.get("team_intl", "International")
            caps = int(player.get("matches_intl", 0) or 0)
            st.plotly_chart(_make_radar(vals_intl, intl_labels, "#60A5FA", f"International ({team_intl})", ""), use_container_width=True)
            st.caption(f"Note Intl : **{float(player.get('rating_intl',0)):.1f}** · {caps} caps")
    else:
        st.markdown("**Radar — 6 axes FIFA**")
        vals_t14 = [float(player.get(a, 50)) for a in t14_axes]
        closed = vals_t14 + [vals_t14[0]]
        cl = t14_labels + [t14_labels[0]]
        fig_radar = go.Figure(go.Scatterpolar(
            r=closed, theta=cl, fill="toself",
            fillcolor="rgba(239,68,68,0.25)",
            line=dict(color="#EF4444", width=2), name=player["name"],
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0,100], tickfont=dict(size=8))),
            showlegend=False, margin=dict(l=30,r=30,t=30,b=30), height=300,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_radar, use_container_width=True)

st.divider()

# --- Courbe d'âge ---
_player_age = _safe_int(player.get("age"), 0)
if _player_age > 0:
    import numpy as _np_age
    _age_x = list(range(17, 40))
    _AGE_PEAK, _AGE_SIGMA, _AGE_AMP, _AGE_OFF = 28.5, 5.0, 4.5, 1.5
    _age_y = [
        float(_np_age.clip(_AGE_AMP * _np_age.exp(-((a - _AGE_PEAK) / _AGE_SIGMA)**2) - _AGE_OFF, -3.0, 3.0))
        for a in _age_x
    ]
    _bar_colors = [
        "#10B981" if a == _player_age else
        ("rgba(16,185,129,0.4)" if v > 0 else "rgba(239,68,68,0.35)")
        for a, v in zip(_age_x, _age_y)
    ]
    _fig_age = go.Figure()
    _fig_age.add_trace(go.Bar(
        x=_age_x, y=_age_y,
        marker_color=_bar_colors,
        text=[f"{v:+.1f}" if a == _player_age else "" for a, v in zip(_age_x, _age_y)],
        textposition="outside",
    ))
    _fig_age.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)
    _fig_age.add_vline(
        x=_player_age, line_color="#F97316", line_dash="dash", line_width=2,
        annotation_text=f"{_player_age} ans ({_af:+.1f} pts)",
        annotation_font_color="#F97316", annotation_position="top right",
    )
    _fig_age.update_layout(
        title=dict(text="Facteur d'âge — bonus/malus sur la note", font=dict(size=13), x=0),
        height=180, margin=dict(l=10, r=10, t=35, b=10),
        yaxis=dict(title="pts", range=[-2, 3.5], gridcolor="#1F2937", zeroline=False),
        xaxis=dict(title="Âge", gridcolor="#1F2937"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(_fig_age, use_container_width=True)

st.divider()

# --- Explain my rating ---
st.subheader("Pourquoi cette note ?")

breakdown = get_rating_breakdown(player_row)
if breakdown:
    minutes_total = float(player.get("matches_played", 15) * player.get("minutes_avg", 60))

    METRIC_LABELS = {
        "tackles_per80": "Plaquages /80", "tackle_success_pct": "% Plaquages",
        "penalties_per80": "Pénalités /80", "turnovers_won_per80": "TO gagnés /80",
        "turnovers_lost_per80": "TO perdus /80", "carries_per80": "Courses /80",
        "meters_per80": "Mètres /80", "line_breaks_per80": "Franchissements /80",
        "offloads_per80": "Offloads /80", "passes_per80": "Passes /80",
        "kick_meters_per80": "Mètres pied /80", "points_scored_per80": "Points /80",
        "errors_per80": "Erreurs /80", "ruck_arrivals_per80": "Rucks /80",
        "lineout_wins_per80": "Touches /80", "scrum_success_pct": "% Mêlée",
    }

    tier = rating_to_tier(player["rating"])
    base = 40.0 + 0.6 * sum(b["contrib"] for b in breakdown) / max(sum(b["weight"] for b in breakdown), 1e-9) * (100 / 100)
    # Recalcul propre pour affichage
    total_w = sum(b["weight"] for b in breakdown)
    raw_score = sum(b["pct"] * b["weight"] for b in breakdown) / total_w if total_w > 0 else 50.0
    base_rating = 40.0 + 0.6 * raw_score
    vol_bonus = 3.0 if minutes_total >= 1400 else (2.0 if minutes_total >= 1100 else (1.0 if minutes_total >= 800 else 0.0))
    pen_item = next((b for b in breakdown if b["metric"] == "penalties_per80"), None)
    pen_pct = pen_item["pct"] if pen_item else 50.0
    disc_malus = 4.0 if pen_pct < 10 else (2.0 if pen_pct < 20 else 0.0)
    cap = next(cap for thresh, cap in [(1400,99),(1100,95),(800,90),(400,84),(200,79),(0,74)] if minutes_total >= thresh)

    confidence_val = float(player.get("confidence", player.get("confidence_score", 50)) )
    if confidence_val > 1:
        confidence_val /= 100  # si stocké en 0-100
    rating_raw_display = float(player.get("rating_raw", player["rating"]))
    rating_final = float(player["rating"])

    ex1, ex2, ex3, ex4 = st.columns(4)
    ex1.metric("Score brut /poste", f"{raw_score:.1f}/100")
    ex2.metric("Note de base", f"{base_rating:.1f}")
    ex3.metric("Bonus volume", f"+{vol_bonus:.0f}", help=f"{minutes_total:.0f} min totales")
    ex4.metric("Malus discipline", f"-{disc_malus:.0f}", delta=f"Plafond gating : {cap}", delta_color="off")

    # Shrinkage info
    sh1, sh2, sh3 = st.columns(3)
    sh1.metric("Note brute (avant ajust.)", f"{rating_raw_display:.1f}")
    sh2.metric("Confiance", f"{confidence_val*100:.0f}%",
               help="60% minutes de jeu + 40% couverture métriques")
    sh3.metric("Note finale (ajustée)", f"{rating_final:.1f}",
               help="note_brute × confiance + moyenne_poste × (1 - confiance)")

    # Graphique des contributions
    bd_df = pd.DataFrame([{
        "Métrique": METRIC_LABELS.get(b["metric"], b["metric"]) + (" ↓" if b["negative"] else ""),
        "Percentile poste": b["pct"],
        "Contribution": b["contrib"],
        "Poids": b["weight"],
    } for b in breakdown]).sort_values("Contribution", ascending=True)

    fig_explain = px.bar(
        bd_df,
        x="Contribution",
        y="Métrique",
        orientation="h",
        color="Percentile poste",
        color_continuous_scale="RdYlGn",
        range_color=[0, 100],
        hover_data={"Poids": True, "Percentile poste": True, "Contribution": True},
        title=f"Contribution de chaque métrique à la note ({player['position_group']})",
    )
    fig_explain.update_layout(
        height=max(250, len(bd_df) * 32 + 80),
        margin=dict(l=10, r=20, t=50, b=10),
        coloraxis_colorbar=dict(title="Percentile", len=0.6),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_explain, use_container_width=True)

    # Tableau détaillé
    with st.expander("Détail complet métrique par métrique"):
        bd_table = pd.DataFrame([{
            "Métrique": METRIC_LABELS.get(b["metric"], b["metric"]),
            "Valeur": b["value"],
            "Négatif ?": "↓ (moins=mieux)" if b["negative"] else "",
            "Percentile poste": f"{b['pct']:.0f}%",
            "Poids": f"{b['weight']:.0%}",
            "Contribution": f"{b['contrib']:.1f}",
        } for b in sorted(breakdown, key=lambda x: x["contrib"], reverse=True)])
        st.dataframe(bd_table, hide_index=True, use_container_width=True)
else:
    st.info("Breakdown non disponible (rechargez la page).")

st.divider()

# --- Stats détaillées ---
st.subheader("Statistiques détaillées (par 80 min)")

# Stats disponibles à 100% (LNR public sans paywall)
REAL_STATS = {
    "tackles_per80":      "Plaquages /80",
    "line_breaks_per80":  "Franchissements /80",
    "offloads_per80":     "Offloads /80",
    "turnovers_won_per80":"Ballons grattés /80",
    "points_scored_per80":"Points /80",
    "tries_per80":        "Essais /80",
    "yellow_cards":       "Cartons jaunes",
    "orange_cards":       "Cartons oranges",
    "red_cards":          "Cartons rouges",
    "minutes_total":      "Minutes totales",
    "matches_played":     "Matchs joués",
    "height_cm":          "Taille (cm)",
    "weight_kg":          "Poids (kg)",
    "age":                "Âge",
}

stat_items = [(lbl, player.get(col)) for col, lbl in REAL_STATS.items()
              if player.get(col) not in (None, "", "nan") and str(player.get(col)) != "nan"
              and float(player.get(col, 0) or 0) != 0]

cols = st.columns(4)
for i, (label, value) in enumerate(stat_items):
    with cols[i % 4]:
        try:
            st.metric(label, f"{float(value):.1f}" if isinstance(value, float) else str(int(float(value))))
        except Exception:
            st.metric(label, str(value))

# --- Forme récente (rolling 5 derniers matchs) ---
form_window = player.get("form_window")
if form_window and not pd.isna(form_window):
    st.divider()
    st.subheader(f"Forme récente ({int(form_window)} derniers matchs)")

    form_metrics = {
        "form_tackles_per80":    ("Plaquages /80",         "tackles_per80"),
        "form_line_breaks_per80":("Franchissements /80",   "line_breaks_per80"),
        "form_offloads_per80":   ("Offloads /80",          "offloads_per80"),
        "form_turnovers_per80":  ("Turnovers gagnés /80",  "turnovers_won_per80"),
    }

    starter_rate = player.get("starter_rate")
    matches_verified = player.get("matches_verified")
    mv_str = f"{int(matches_verified)} matchs vérifiés" if matches_verified and not pd.isna(matches_verified) else ""
    sr_str = f"{starter_rate:.0%} titulaire" if starter_rate and not pd.isna(starter_rate) else ""
    if mv_str or sr_str:
        st.caption(" · ".join(filter(None, [mv_str, sr_str])))

    form_cols = st.columns(len(form_metrics))
    for col_ui, (form_col, (label, season_col)) in zip(form_cols, form_metrics.items()):
        form_val = player.get(form_col)
        season_val = player.get(season_col)
        if form_val is not None and not pd.isna(form_val):
            delta_str = None
            if season_val is not None and not pd.isna(season_val) and float(season_val) > 0:
                delta_val = float(form_val) - float(season_val)
                delta_str = f"{delta_val:+.1f} vs saison"
            col_ui.metric(
                label,
                f"{float(form_val):.1f}",
                delta=delta_str,
            )
        else:
            col_ui.metric(label, "N/A")

    # Sparkline — évolution match par match (5 derniers)
    spark_raw = player.get("form_scores_list")
    if isinstance(spark_raw, str):
        import ast
        try:
            spark_raw = ast.literal_eval(spark_raw)
        except Exception:
            spark_raw = []
    if isinstance(spark_raw, list) and len(spark_raw) >= 2:
        import numpy as _np_form
        n_sp = len(spark_raw)
        x_sp = [f"M-{n_sp - j}" for j in range(n_sp)]
        avg_sp = float(_np_form.mean(spark_raw))
        trend = player.get("form_trend", "→")
        trend_color = {"↗": "#10B981", "↘": "#EF4444", "→": "#9CA3AF"}.get(trend, "#9CA3AF")
        bar_colors = ["#10B981" if s >= avg_sp else "#374151" for s in spark_raw]
        import plotly.graph_objects as _go_spark
        fig_sp = _go_spark.Figure()
        fig_sp.add_trace(_go_spark.Bar(
            x=x_sp, y=spark_raw,
            marker_color=bar_colors,
            text=[f"{s:.0f}" for s in spark_raw],
            textposition="outside",
        ))
        fig_sp.add_hline(y=avg_sp, line_dash="dot", line_color="#9CA3AF",
                          annotation_text="moy", annotation_position="bottom right")
        fig_sp.update_layout(
            title=dict(
                text=f'<b style="color:{trend_color}">{trend}</b> Sparkline forme (score /100)',
                font=dict(size=13), x=0,
            ),
            height=200,
            margin=dict(l=5, r=5, t=35, b=5),
            yaxis=dict(range=[0, 115], showticklabels=False),
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_sp, use_container_width=True)

# --- Consistance ---
_cons_val = player.get("axis_consistency")
_n_cons = player.get("n_matches_consistency")
if _cons_val is not None and str(_cons_val) not in ("nan", ""):
    try:
        _cv = float(_cons_val)
        st.divider()
        _cons_label = "Très régulier" if _cv >= 80 else ("Régulier" if _cv >= 55 else ("Irrégulier" if _cv >= 30 else "Très irrégulier"))
        _cons_color = "#10B981" if _cv >= 80 else ("#86EFAC" if _cv >= 55 else ("#F59E0B" if _cv >= 30 else "#EF4444"))
        _n_str = f" · {int(_n_cons)} matchs analysés" if _n_cons and str(_n_cons) != "nan" else ""
        st.markdown(
            f"""<div style="background:#111827;border:1px solid #1F2937;border-radius:12px;padding:14px 20px;margin-bottom:8px">
              <div style="font-size:0.75em;color:#9CA3AF;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px">
                📈 Consistance de performance{_n_str}
              </div>
              <div style="display:flex;align-items:center;gap:16px">
                <span style="font-size:1.8em;font-weight:700;color:{_cons_color}">{_cv:.0f}<span style="font-size:0.5em;color:#9CA3AF">/100</span></span>
                <div style="flex:1">
                  <div style="background:#1F2937;border-radius:6px;height:8px;overflow:hidden">
                    <div style="width:{_cv:.0f}%;height:100%;background:{_cons_color};border-radius:6px;transition:width .5s"></div>
                  </div>
                  <div style="color:{_cons_color};font-size:0.85em;margin-top:4px">{_cons_label}</div>
                </div>
              </div>
              <div style="font-size:0.75em;color:#6B7280;margin-top:6px">
                Coefficient de variation inversé sur plaquages, offloads, franchissements, grattages.
                100 = performance identique à chaque match.
              </div>
            </div>""",
            unsafe_allow_html=True,
        )
    except (TypeError, ValueError):
        pass

# ================================================================
# Historique par saison
# ================================================================
import os as _os
if _os.path.exists(ALL_SEASONS_PATH):
    st.divider()
    st.subheader("Progression historique")
    df_all = pd.read_csv(ALL_SEASONS_PATH)
    # Chercher le joueur par slug (plus fiable) puis par nom
    slug = player.get("lnr_slug", "")
    if slug and "lnr_slug" in df_all.columns:
        hist = df_all[df_all["lnr_slug"] == slug]
    else:
        hist = df_all[df_all["name"].str.upper() == str(player.get("name","")).upper()]
    if not hist.empty and "season" in hist.columns and "rating" in hist.columns:
        hist = hist.sort_values("season")
        fig_hist = px.line(
            hist, x="season", y="rating",
            markers=True,
            labels={"season": "Saison", "rating": "Note"},
            title=f"Évolution de la note — {player['name']}",
        )
        if "rating_value" in hist.columns:
            fig_hist.add_scatter(x=hist["season"], y=hist["rating_value"],
                                 mode="lines+markers", name="Note Valeur",
                                 line=dict(dash="dot", color="#60A5FA"))
        fig_hist.add_hline(y=70, line_dash="dash", line_color="#6B7280",
                           annotation_text="Seuil BRONZE")
        fig_hist.add_hline(y=77, line_dash="dash", line_color="#10B981",
                           annotation_text="Seuil ARGENT")
        fig_hist.update_layout(
            height=300, margin=dict(l=10,r=10,t=50,b=10),
            paper_bgcolor="rgba(0,0,0,0)", legend=dict(x=0, y=1),
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.caption("Données historiques insuffisantes pour ce joueur.")

# ================================================================
# Joueurs similaires (distance euclidienne sur les 6 axes)
# ================================================================
st.divider()
st.subheader("Joueurs similaires")

_axes_sim = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow", "axis_gabarit", "axis_consistency"]
_sim_pool = df[df["position_group"] == player["position_group"]].copy()
_sim_pool = _sim_pool[_sim_pool["name"] != player["name"]]

if not _sim_pool.empty and all(a in _sim_pool.columns for a in _axes_sim):
    import numpy as _np
    p_vec = _np.array([float(player.get(a, 50)) for a in _axes_sim])
    _sim_pool = _sim_pool.copy()
    _sim_pool["_dist"] = _sim_pool[_axes_sim].apply(
        lambda row: float(_np.linalg.norm(row.values.astype(float) - p_vec)), axis=1
    )
    top_sim = _sim_pool.nsmallest(6, "_dist")[
        ["name", "team", "rating", "rating_intl"] + _axes_sim
    ].reset_index(drop=True)
    top_sim.index += 1
    col_sim_labels = {"name": "Joueur", "team": "Equipe", "rating": "Note T14",
                      "rating_intl": "🌍 Note Intl",
                      "axis_att": "Course", "axis_def": "Physique", "axis_disc": "Rigueur",
                      "axis_ctrl": "Distrib", "axis_kick": "Kicking", "axis_pow": "Danger"}
    disp_sim = top_sim[[c for c in top_sim.columns if c in col_sim_labels]].rename(columns=col_sim_labels)
    sim_grad = [c for c in ["Note T14", "Course", "Physique", "Rigueur", "Distrib", "Kicking", "Danger"] if c in disp_sim.columns]
    st.dataframe(
        disp_sim.style.background_gradient(subset=sim_grad, cmap="Blues"),
        use_container_width=True, hide_index=False,
    )
else:
    st.caption("Pas assez de joueurs au même poste pour calculer la similarité.")
