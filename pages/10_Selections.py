"""
Page 10 — XV par Sélection
Visualise le XV optimal d'une nation parmi les joueurs actuellement en Top14.
Deux sections :
  1. XV Top14 d'une nation (carte + radar)
  2. Confrontation deux nations (radar superposé + tableau comparatif)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils import page_config, load_data, AXIS_LABELS

page_config("XV par Sélection")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Mapping position_group → slots XV avec ordre d'affichage
# (slot_id, label_court, label_long, position_group, max_joueurs)
XV_SLOTS = [
    ("Pilier G",      "1. Pilier G",      "FRONT_ROW"),
    ("Talonneur",     "2. Talonneur",     "FRONT_ROW"),
    ("Pilier D",      "3. Pilier D",      "FRONT_ROW"),
    ("2e Ligne G",    "4. 2e Ligne",      "LOCK"),
    ("2e Ligne D",    "5. 2e Ligne",      "LOCK"),
    ("Flanker G",     "6. Flanker G",     "BACK_ROW"),
    ("N°8",           "8. N°8",           "BACK_ROW"),
    ("Flanker D",     "7. Flanker D",     "BACK_ROW"),
    ("Demi mêlée",    "9. Demi mêlée",    "SCRUM_HALF"),
    ("Ouvreur",       "10. Ouvreur",      "FLY_HALF"),
    ("Ailier G",      "11. Ailier G",     "WINGER"),
    ("Centre G",      "12. Centre G",     "CENTRE"),
    ("Centre D",      "13. Centre D",     "CENTRE"),
    ("Ailier D",      "14. Ailier D",     "WINGER"),
    ("Arrière",       "15. Arrière",      "FULLBACK"),
]

# Nombre de joueurs à prendre par groupe de poste
GROUP_QUOTA = {
    "FRONT_ROW":  3,
    "LOCK":       2,
    "BACK_ROW":   3,
    "SCRUM_HALF": 1,
    "FLY_HALF":   1,
    "WINGER":     2,
    "CENTRE":     2,
    "FULLBACK":   1,
}

AXIS_COLS_T14 = list(AXIS_LABELS.keys())  # axis_att, axis_def, axis_disc, axis_ctrl, axis_kick, axis_pow
AXIS_NAMES_T14 = list(AXIS_LABELS.values())

NATION_FLAG = {
    "France": "🇫🇷", "All Blacks": "🇳🇿", "Irlande": "🇮🇪",
    "SA": "🇿🇦", "Angleterre": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Australie": "🇦🇺",
    "Argentine": "🇦🇷", "SCOT": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "WALES": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "ITALY": "🇮🇹", "Japon": "🇯🇵", "FIJI": "🇫🇯",
    "SAMOA": "🇼🇸", "TONGA": "🇹🇴", "GEORG": "🇬🇪",
    "Roumanie": "🇷🇴", "URUG": "🇺🇾", "NAMIB": "🇳🇦",
    "Chili": "🇨🇱", "PORT": "🇵🇹",
}

# ---------------------------------------------------------------------------
# Chargement données
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_players_scored() -> pd.DataFrame:
    df = load_data("2025-2026")
    return df


@st.cache_data(ttl=3600)
def load_intl() -> pd.DataFrame:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "international_ratings.csv")
    return pd.read_csv(path)


df_t14 = load_players_scored()
try:
    df_intl = load_intl()
except FileNotFoundError:
    df_intl = pd.DataFrame()

# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

def get_nations(df: pd.DataFrame) -> list[str]:
    """Retourne les nations disponibles triées, France en tête."""
    nations = sorted(df["team_intl"].dropna().unique().tolist())
    if "France" in nations:
        nations = ["France"] + [n for n in nations if n != "France"]
    return nations


def build_xv(df: pd.DataFrame, nation: str) -> list[dict]:
    """
    Construit le XV optimal d'une nation à partir des joueurs Top14.
    Retourne une liste de 15 dicts (un par slot), avec None si joueur indisponible.
    """
    pool = df[df["team_intl"] == nation].copy()
    # Trier par rating desc pour sélectionner les meilleurs
    pool = pool.sort_values("rating", ascending=False)

    # Compteurs d'attribution par groupe de poste
    used_indices: dict[str, list] = {g: [] for g in GROUP_QUOTA}

    result = []
    for slot_label, slot_full, pos_group in XV_SLOTS:
        already_used = len(used_indices[pos_group])
        quota = GROUP_QUOTA[pos_group]

        candidates = pool[
            (pool["position_group"] == pos_group) &
            (~pool.index.isin(used_indices[pos_group]))
        ]

        if candidates.empty or already_used >= quota:
            result.append({
                "slot": slot_label,
                "slot_full": slot_full,
                "pos_group": pos_group,
                "player": None,
            })
        else:
            player = candidates.iloc[0]
            used_indices[pos_group].append(player.name)
            result.append({
                "slot": slot_label,
                "slot_full": slot_full,
                "pos_group": pos_group,
                "player": player,
            })
    return result


def xv_to_df(xv: list[dict]) -> pd.DataFrame:
    """Convertit le XV en DataFrame pour affichage."""
    rows = []
    for entry in xv:
        p = entry["player"]
        if p is not None:
            rows.append({
                "Poste": entry["slot_full"],
                "Joueur": p.get("name", "N/A"),
                "Club": p.get("team", "N/A"),
                "Note T14": round(float(p.get("rating", 0)), 1),
                "Note Intl": round(float(p.get("rating_intl", 0)), 1) if pd.notna(p.get("rating_intl")) else None,
                **{AXIS_LABELS[ax]: round(float(p.get(ax, 0)), 1) for ax in AXIS_COLS_T14},
            })
        else:
            rows.append({
                "Poste": entry["slot_full"],
                "Joueur": "N/A",
                "Club": "—",
                "Note T14": None,
                "Note Intl": None,
                **{AXIS_LABELS[ax]: None for ax in AXIS_COLS_T14},
            })
    return pd.DataFrame(rows)


def xv_radar_mean(xv: list[dict]) -> list[float]:
    """Calcule la moyenne des 6 axes Top14 du XV sélectionné."""
    vals = {ax: [] for ax in AXIS_COLS_T14}
    for entry in xv:
        p = entry["player"]
        if p is not None:
            for ax in AXIS_COLS_T14:
                v = p.get(ax)
                if pd.notna(v):
                    vals[ax].append(float(v))
    return [
        round(sum(vals[ax]) / len(vals[ax]), 1) if vals[ax] else 0.0
        for ax in AXIS_COLS_T14
    ]


def radar_figure(traces: list[dict], title: str = "") -> go.Figure:
    """
    Crée un radar Plotly.
    traces : liste de {"name": str, "values": [float x 6], "color": str}
    """
    fig = go.Figure()
    for t in traces:
        vals = t["values"]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=AXIS_NAMES_T14 + [AXIS_NAMES_T14[0]],
            fill="toself",
            name=t["name"],
            line_color=t["color"],
            opacity=0.72,
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        title=title,
        height=420,
        margin=dict(l=60, r=60, t=50, b=40),
    )
    return fig


RADAR_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

# ---------------------------------------------------------------------------
# UI — En-tête
# ---------------------------------------------------------------------------

st.title("XV par Sélection")
st.markdown(
    "Sélectionne une nation pour visualiser son **XV optimal** parmi les joueurs "
    "actuellement en **Top14 2025-2026**. "
    "La note Top14 reflète la performance en club cette saison ; "
    "la note Internationale provient de l'analyse ESPN Tests 2016–2024."
)

nations_available = get_nations(df_t14)
if not nations_available:
    st.error("Colonne `team_intl` introuvable dans players_scored.csv.")
    st.stop()

# ============================================================
# SECTION 1 — XV Top14 par nation
# ============================================================

st.markdown("---")
st.header("XV Top14 par nation")

col_sel, col_info = st.columns([2, 3])
with col_sel:
    nation_1 = st.selectbox(
        "Nation",
        nations_available,
        format_func=lambda n: f"{NATION_FLAG.get(n, '')} {n}",
        key="nation_sel_1",
    )

xv_1 = build_xv(df_t14, nation_1)
df_xv_1 = xv_to_df(xv_1)

n_available = sum(1 for e in xv_1 if e["player"] is not None)
flag_1 = NATION_FLAG.get(nation_1, "")

with col_info:
    st.metric("Joueurs disponibles (Top14)", f"{n_available} / 15")
    if n_available < 15:
        st.warning(
            f"La sélection {nation_1} n'a que **{n_available} joueurs** en Top14 "
            "pour couvrir les 15 postes. Les postes manquants affichent N/A."
        )

# --- Carte du XV ---
st.subheader(f"{flag_1} {nation_1} — XV optimal en Top14")

display_df = df_xv_1[["Poste", "Joueur", "Club", "Note T14", "Note Intl"]].copy()

# Mise en forme : None → "N/A"
def fmt_note(v):
    return f"{v:.1f}" if pd.notna(v) and v is not None else "N/A"

styled = display_df.style.format({
    "Note T14": fmt_note,
    "Note Intl": fmt_note,
}).background_gradient(
    subset=["Note T14"],
    cmap="YlOrRd",
    vmin=60,
    vmax=95,
)
st.dataframe(styled, use_container_width=True, height=570)

# --- Radar du XV ---
means_1 = xv_radar_mean(xv_1)

if n_available > 0:
    st.subheader(f"Profil moyen du XV — {flag_1} {nation_1}")
    st.caption("Moyenne des 6 axes Top14 des joueurs sélectionnés.")
    fig_r1 = radar_figure(
        [{"name": f"{flag_1} {nation_1}", "values": means_1, "color": RADAR_COLORS[0]}],
        title=f"Radar XV — {nation_1}",
    )
    st.plotly_chart(fig_r1, use_container_width=True)

# --- Détail axes par joueur ---
with st.expander("Voir le détail des axes par joueur"):
    axis_display_cols = ["Poste", "Joueur"] + list(AXIS_LABELS.values())
    df_axes = df_xv_1[[c for c in axis_display_cols if c in df_xv_1.columns]].copy()
    numeric_axis = list(AXIS_LABELS.values())
    existing_axis = [c for c in numeric_axis if c in df_axes.columns]
    styled_axes = df_axes.style.format(
        {col: lambda v: f"{v:.1f}" if pd.notna(v) and v is not None else "N/A" for col in existing_axis}
    ).background_gradient(subset=existing_axis, cmap="Blues", vmin=40, vmax=100)
    st.dataframe(styled_axes, use_container_width=True)

# ============================================================
# SECTION 2 — Confrontation deux nations
# ============================================================

st.markdown("---")
st.header("Confrontation deux nations")
st.markdown("Compare les XV optimaux de deux nations en Top14 : radar superposé et tableau côte à côte.")

col_a, col_b = st.columns(2)
with col_a:
    nation_a = st.selectbox(
        "Nation A",
        nations_available,
        format_func=lambda n: f"{NATION_FLAG.get(n, '')} {n}",
        key="nation_conf_a",
        index=0,
    )
with col_b:
    default_b_idx = 1 if len(nations_available) > 1 else 0
    nation_b = st.selectbox(
        "Nation B",
        nations_available,
        format_func=lambda n: f"{NATION_FLAG.get(n, '')} {n}",
        key="nation_conf_b",
        index=default_b_idx,
    )

if nation_a == nation_b:
    st.info("Sélectionne deux nations différentes pour la confrontation.")
else:
    flag_a = NATION_FLAG.get(nation_a, "")
    flag_b = NATION_FLAG.get(nation_b, "")

    xv_a = build_xv(df_t14, nation_a)
    xv_b = build_xv(df_t14, nation_b)
    means_a = xv_radar_mean(xv_a)
    means_b = xv_radar_mean(xv_b)

    n_a = sum(1 for e in xv_a if e["player"] is not None)
    n_b = sum(1 for e in xv_b if e["player"] is not None)

    col_m1, col_m2 = st.columns(2)
    col_m1.metric(f"{flag_a} {nation_a} — joueurs dispo", f"{n_a} / 15")
    col_m2.metric(f"{flag_b} {nation_b} — joueurs dispo", f"{n_b} / 15")

    # --- Radar superposé ---
    st.subheader("Radar superposé — Profil moyen des deux XV")
    fig_cmp = radar_figure(
        [
            {"name": f"{flag_a} {nation_a}", "values": means_a, "color": RADAR_COLORS[0]},
            {"name": f"{flag_b} {nation_b}", "values": means_b, "color": RADAR_COLORS[1]},
        ],
        title=f"{nation_a} vs {nation_b}",
    )
    st.plotly_chart(fig_cmp, use_container_width=True)

    # --- Bar chart comparatif des axes ---
    st.subheader("Comparaison des axes")
    axes_comp = pd.DataFrame({
        "Axe": AXIS_NAMES_T14,
        nation_a: means_a,
        nation_b: means_b,
    })
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        name=f"{flag_a} {nation_a}",
        x=axes_comp["Axe"],
        y=axes_comp[nation_a],
        marker_color=RADAR_COLORS[0],
        text=[f"{v:.1f}" for v in means_a],
        textposition="outside",
    ))
    fig_bar.add_trace(go.Bar(
        name=f"{flag_b} {nation_b}",
        x=axes_comp["Axe"],
        y=axes_comp[nation_b],
        marker_color=RADAR_COLORS[1],
        text=[f"{v:.1f}" for v in means_b],
        textposition="outside",
    ))
    fig_bar.update_layout(
        barmode="group",
        yaxis=dict(range=[0, 110]),
        height=380,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- Tableau comparatif des 15 postes ---
    st.subheader("Tableau comparatif poste par poste")

    df_a = xv_to_df(xv_a)[["Poste", "Joueur", "Club", "Note T14", "Note Intl"]]
    df_b = xv_to_df(xv_b)[["Joueur", "Club", "Note T14", "Note Intl"]]

    df_compare = df_a.copy()
    df_compare = df_compare.rename(columns={
        "Joueur": f"Joueur {flag_a}",
        "Club":   f"Club {flag_a}",
        "Note T14": f"T14 {flag_a}",
        "Note Intl": f"Intl {flag_a}",
    })
    df_compare[f"Joueur {flag_b}"] = df_b["Joueur"].values
    df_compare[f"Club {flag_b}"]   = df_b["Club"].values
    df_compare[f"T14 {flag_b}"]    = df_b["Note T14"].values
    df_compare[f"Intl {flag_b}"]   = df_b["Note Intl"].values

    note_cols = [f"T14 {flag_a}", f"Intl {flag_a}", f"T14 {flag_b}", f"Intl {flag_b}"]
    fmt_dict = {col: fmt_note for col in note_cols}

    styled_cmp = df_compare.style.format(fmt_dict)
    # Gradient sur les notes T14
    t14_cols = [f"T14 {flag_a}", f"T14 {flag_b}"]
    existing_t14 = [c for c in t14_cols if c in df_compare.columns]
    if existing_t14:
        styled_cmp = styled_cmp.background_gradient(subset=existing_t14, cmap="YlOrRd", vmin=60, vmax=95)

    st.dataframe(styled_cmp, use_container_width=True, height=570)

    # --- Résumé statistique ---
    with st.expander("Résumé statistique des deux XV"):
        summary_data = {
            "Métrique": ["Joueurs disponibles", "Note T14 moyenne", "Note Intl moyenne"] + AXIS_NAMES_T14,
        }
        df_a_full = xv_to_df(xv_a)
        df_b_full = xv_to_df(xv_b)

        def safe_mean(series):
            vals = [v for v in series if pd.notna(v) and v is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        vals_a = [n_a,
                  safe_mean(df_a_full["Note T14"]),
                  safe_mean(df_a_full["Note Intl"])]
        vals_b = [n_b,
                  safe_mean(df_b_full["Note T14"]),
                  safe_mean(df_b_full["Note Intl"])]

        for ax_name in AXIS_NAMES_T14:
            vals_a.append(safe_mean(df_a_full[ax_name]) if ax_name in df_a_full.columns else None)
            vals_b.append(safe_mean(df_b_full[ax_name]) if ax_name in df_b_full.columns else None)

        summary_data[f"{flag_a} {nation_a}"] = vals_a
        summary_data[f"{flag_b} {nation_b}"] = vals_b

        df_summary = pd.DataFrame(summary_data)
        st.dataframe(df_summary, use_container_width=True, hide_index=True)
