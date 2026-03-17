"""
Page 1 — Cartes joueur style FIFA
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from utils import load_data, page_config, AXIS_LABELS, AXIS_COLORS, rating_to_tier, TIER_COLORS, AXIS_DESCRIPTIONS, get_available_positions, get_photo_url, fetch_player_photo_bytes, season_selector
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

if photo_bytes:
    col_photo, col_header = st.columns([1, 3], gap="large")
    with col_photo:
        st.image(photo_bytes, use_container_width=True)
    with col_header:
        st.markdown(
            f'<h2 style="margin:0;font-size:2em">{player["name"]}</h2>'
            f'<p style="margin:4px 0;color:#9CA3AF;font-size:1em">'
            f'{player.get("position_label", player["position_group"])} · {player["team"]}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="display:inline-block;margin-top:8px;padding:6px 16px;'
            f'background:{tier_color}22;border:1px solid {tier_color};border-radius:8px">'
            f'<b style="color:{tier_color};font-size:1.4em">{player["rating"]:.1f}</b>'
            f'&nbsp;<span style="color:{tier_color}">{tier}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.divider()

# --- Layout carte FIFA + détails ---
col_card, col_details = st.columns([1, 2], gap="large")

with col_card:
    card_bytes = render_card(player)
    st.image(card_bytes, use_container_width=True)

    if not photo_bytes:
        # Afficher tier badge sous la carte si pas de photo header
        st.markdown(
            f'<div style="text-align:center;padding:6px;background:{tier_color}22;'
            f'border:1px solid {tier_color};border-radius:8px;margin-top:8px">'
            f'<b style="color:{tier_color}">{tier}</b> — Note globale : '
            f'<b style="font-size:1.2em">{player["rating"]:.1f}</b>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.download_button(
        "Télécharger la carte (PNG)",
        data=card_bytes,
        file_name=f"carte_{selected_name.replace(' ', '_')}.png",
        mime="image/png",
        use_container_width=True,
    )

with col_details:
    if not photo_bytes:
        st.subheader(player["name"])
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Equipe", player["team"])
    i2.metric("Poste", player.get("position_label", player["position_group"]))
    i3.metric("Nationalité", player.get("nationality", "?"))
    i4.metric("Age", int(player.get("age", 0)))

    st.markdown("**Profil physique**")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Taille", f"{int(player.get('height_cm', 0))} cm")
    p2.metric("Poids", f"{int(player.get('weight_kg', 0))} kg")
    p3.metric("Matchs joués", int(player.get("matches_played", 0)))
    if "minutes_avg" in player:
        p4.metric("Min. moyennes", f"{player['minutes_avg']:.0f}")

    # Confidence badge + rank intra-poste
    conf_badge = player.get("confidence_badge", "")
    conf = int(player.get("confidence_score", 50))
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

    st.markdown("**Radar — 6 axes FIFA**")
    axes = ["axis_att", "axis_def", "axis_disc", "axis_ctrl", "axis_kick", "axis_pow"]
    labels = [AXIS_LABELS[a] for a in axes]
    values = [player.get(a, 50) for a in axes]
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]

    fig_radar = go.Figure(go.Scatterpolar(
        r=values_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor="rgba(239,68,68,0.25)",
        line=dict(color="#EF4444", width=2),
        name=player["name"],
    ))
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=8)),
            angularaxis=dict(tickfont=dict(size=11)),
        ),
        showlegend=False,
        margin=dict(l=30, r=30, t=30, b=30),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_radar, use_container_width=True)

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

stat_cols = [
    "tackles_per80", "tackle_success_pct", "penalties_per80",
    "turnovers_won_per80", "turnovers_lost_per80", "carries_per80",
    "meters_per80", "line_breaks_per80", "offloads_per80",
    "passes_per80", "kick_meters_per80", "points_scored_per80",
    "errors_per80", "ruck_arrivals_per80", "lineout_wins_per80",
    "scrum_success_pct",
]

labels_map = {
    "tackles_per80": "Plaquages /80",
    "tackle_success_pct": "% Plaquages réussis",
    "penalties_per80": "Pénalités /80",
    "turnovers_won_per80": "Turnovers gagnés /80",
    "turnovers_lost_per80": "Turnovers perdus /80",
    "carries_per80": "Courses /80",
    "meters_per80": "Mètres gagnés /80",
    "line_breaks_per80": "Franchissements /80",
    "offloads_per80": "Offloads /80",
    "passes_per80": "Passes /80",
    "kick_meters_per80": "Mètres au pied /80",
    "points_scored_per80": "Points marqués /80",
    "errors_per80": "Erreurs /80",
    "ruck_arrivals_per80": "Arrivées au ruck /80",
    "lineout_wins_per80": "Touches gagnées /80",
    "scrum_success_pct": "% Réussite mêlée",
}

# Afficher en grille 4 colonnes
stat_items = [(labels_map.get(s, s), player.get(s, "N/A")) for s in stat_cols if s in player]

cols = st.columns(4)
for i, (label, value) in enumerate(stat_items):
    with cols[i % 4]:
        if isinstance(value, float):
            st.metric(label, f"{value:.1f}")
        else:
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
            delta = None
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
