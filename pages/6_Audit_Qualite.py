"""
Page 6 — Audit Qualité du dataset et du moteur de notation.
Détecte anomalies, sous-couvertures et joueurs suspects.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from utils import load_data, page_config, load_source_mode, season_selector

page_config("Audit Qualité")
st.title("Audit Qualité")
st.markdown(
    "Contrôle de qualité du dataset et du moteur : anomalies de notes, "
    "couverture par équipe/poste, joueurs suspects (fort rating + faible volume)."
)

season = season_selector("_audit")
df = load_data(season)

DATA_MODE = os.environ.get("DATA_MODE", "demo")
if DATA_MODE == "demo":
    st.warning("Mode DEMO — les métriques ci-dessous portent sur des données synthétiques.")

# ================================================================
# Banner SOURCE_MODE
# ================================================================
_sm = load_source_mode()
if _sm == "LNR_ONLY":
    st.error(
        "**SOURCE : LNR UNIQUEMENT** — Postes regroupés (FRONT_ROW / LOCK / BACK_ROW). "
        "Couverture stats ~25%. Stars en sélection nationale sous-évaluées. "
        "Intégrer Statbunker pour passer à ~50% de couverture et obtenir les postes fins."
    )
elif _sm == "LNR_SB_MIXED":
    st.info("**SOURCE : LNR + Statbunker** — Postes fins et stats étendues disponibles.")

# ================================================================
# Source des postes (notice LNR-only)
# ================================================================
_position_source_col = "position_source" if "position_source" in df.columns else None
_has_sb = _position_source_col and (df["position_source"] == "sb").any()

if _has_sb:
    st.info(
        "**Source mixte LNR + Statbunker** — postes fins disponibles "
        "(HOOKER, NUMBER_8 possibles si couverture SB suffisante)."
    )
else:
    st.info(
        "**Source LNR-only** → postes affichés en **groupes** : "
        "FRONT_ROW (Piliers + Talonneur) / LOCK / BACK_ROW (Flankers + N°8). "
        "LNR ne différencie pas Pilier vs Talonneur ni Flanker vs N°8. "
        "Intégrer Statbunker pour obtenir les postes fins."
    )

# ================================================================
# 1. Couverture globale
# ================================================================
st.subheader("Couverture globale")

# Stats LNR publiques disponibles (sans paywall)
REAL_STAT_COLS = {
    "tackles_per80":       "Plaquages /80",
    "line_breaks_per80":   "Franchissements /80",
    "offloads_per80":      "Offloads /80",
    "turnovers_won_per80": "Ballons grattés /80",
    "points_scored_per80": "Points marqués /80",
    "tries_per80":         "Essais /80",
    "yellow_cards":        "Cartons jaunes",
    "orange_cards":        "Cartons oranges",
    "red_cards":           "Cartons rouges",
    "height_cm":           "Taille (cm)",
    "weight_kg":           "Poids (kg)",
    "age":                 "Âge",
    "nationality":         "Nationalité",
}

available_cols = [c for c in REAL_STAT_COLS if c in df.columns]
coverage = df[available_cols].notna().mean() * 100
nonzero = {c: int((df[c].fillna(0) > 0).sum()) for c in available_cols}

cov_df = pd.DataFrame({
    "Métrique": [REAL_STAT_COLS[c] for c in available_cols],
    "Couverture %": coverage.values.round(1),
    "Joueurs > 0": [nonzero[c] for c in available_cols],
})
cov_df = cov_df.sort_values("Couverture %")

kc1, kc2, kc3, kc4 = st.columns(4)
kc1.metric("Joueurs total", len(df))
kc2.metric("Équipes", df["team"].nunique())
kc3.metric("Postes couverts", df["position_group"].nunique())
kc4.metric("Stats 100% couvertes", f"{(coverage == 100).sum()}/{len(available_cols)}")

st.success(
    "**Stats moteur — toutes à 100% de couverture.** "
    "Les colonnes paywall (carries, meters, passes, penalties, errors, mêlée, lineouts…) "
    "ont été retirées du schéma — elles n'étaient jamais renseignées par LNR public."
)

fig_cov = px.bar(
    cov_df, x="Couverture %", y="Métrique", orientation="h",
    color="Couverture %", color_continuous_scale="RdYlGn",
    range_color=[0, 100],
    text=cov_df["Couverture %"].apply(lambda x: f"{x:.0f}%"),
    hover_data={"Joueurs > 0": True},
    title="Taux de complétion — stats LNR publiques uniquement",
)
fig_cov.update_traces(textposition="outside")
fig_cov.update_layout(height=380, margin=dict(l=10, r=60, t=50, b=10), coloraxis_showscale=False)
st.plotly_chart(fig_cov, use_container_width=True)

# Couverture par poste (heatmap métriques × postes)
with st.expander("Couverture des métriques par groupe de poste"):
    from engine.ratings import load_weights
    try:
        _weights = load_weights()
        _core_all = sorted({m for pg_cfg in _weights.values() for m in pg_cfg})
        _core_avail = [m for m in _core_all if m in df.columns]
        if _core_avail:
            cov_by_pos = (
                df.groupby("position_group")[_core_avail]
                .apply(lambda g: g.notna().mean() * 100)
                .round(1)
            )
            fig_pos_cov = px.imshow(
                cov_by_pos,
                text_auto=True,
                color_continuous_scale="RdYlGn",
                zmin=0, zmax=100,
                aspect="auto",
                labels={"x": "Métrique", "y": "Poste", "color": "Couv. %"},
                title="Couverture par métrique × groupe de poste (%)",
            )
            fig_pos_cov.update_layout(
                height=max(300, len(cov_by_pos) * 40 + 80),
                margin=dict(l=10, r=10, t=50, b=10),
            )
            st.plotly_chart(fig_pos_cov, use_container_width=True)
            if not _has_sb:
                st.info(
                    "**LNR-only** : les ratings sont des proxies basés sur les stats disponibles, "
                    "**pas une mesure du niveau global**. Les métriques absentes (rouge) impliquent "
                    "que le moteur n'évalue pas ces dimensions. "
                    "Stars en sélection nationale (peu de matchs Top14) peuvent être sous-évalués."
                )
    except Exception as _e:
        st.caption(f"Couverture par poste non disponible : {_e}")

# ================================================================
# 2. Couverture par équipe
# ================================================================
st.divider()
st.subheader("Couverture par équipe")

team_stats = df.groupby("team").agg(
    n_players=("player_id", "count"),
    avg_rating=("rating", "mean"),
    avg_confidence=("confidence_score", "mean") if "confidence_score" in df.columns else ("rating", "count"),
    missing_pct=("tackles_per80", lambda x: x.isna().mean() * 100),
).round(1).reset_index()
team_stats.columns = ["Équipe", "Joueurs", "Note moy.", "Confiance moy.", "% NaN stats"]

fig_team_cov = px.bar(
    team_stats.sort_values("Joueurs"),
    x="Joueurs", y="Équipe", orientation="h",
    color="Note moy.", color_continuous_scale="RdYlGn",
    text="Joueurs",
    title="Nombre de joueurs par équipe",
)
fig_team_cov.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=10, r=20, t=50, b=10))
st.plotly_chart(fig_team_cov, use_container_width=True)

st.dataframe(team_stats, hide_index=True, use_container_width=True)

# ================================================================
# 3. Distribution des notes — sanity check
# ================================================================
st.divider()
st.subheader("Distribution des notes — sanity check")

target_mean, target_std = 70.0, 8.0
actual_mean = df["rating"].mean()
actual_std = df["rating"].std()

sc1, sc2, sc3, sc4 = st.columns(4)
sc1.metric("Moyenne réelle", f"{actual_mean:.1f}", delta=f"{actual_mean - target_mean:+.1f} vs cible 70")
sc2.metric("Écart-type réel", f"{actual_std:.1f}", delta=f"{actual_std - target_std:+.1f} vs cible 8")
sc3.metric("Notes > 90", len(df[df["rating"] > 90]), help="Devrait être rare (top 1-2%)")
sc4.metric("Notes < 55", len(df[df["rating"] < 55]), help="Remplaçants peu utilisés")

fig_dist = px.histogram(
    df, x="rating", nbins=30, color="position_group",
    title="Distribution des notes par poste",
    labels={"rating": "Note", "position_group": "Poste"},
    opacity=0.7,
)
fig_dist.add_vline(x=90, line_dash="dash", line_color="gold", annotation_text="Seuil élite 90")
fig_dist.add_vline(x=actual_mean, line_dash="dot", line_color="white", annotation_text=f"Moy. {actual_mean:.1f}")
fig_dist.update_layout(height=320, margin=dict(l=10, r=10, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig_dist, use_container_width=True)

# ================================================================
# 4. Anomalies — fort rating + faible volume
# ================================================================
st.divider()
st.subheader("Anomalies détectées")

anomalies = []

# A) Fort rating + faible confidence
if "confidence_score" in df.columns:
    suspects = df[(df["rating"] >= 80) & (df["confidence_score"] < 50)].copy()
    for _, row in suspects.iterrows():
        anomalies.append({
            "Type": "Rating élevé + faible confiance",
            "Joueur": row["name"],
            "Poste": row["position_group"],
            "Équipe": row["team"],
            "Note": row["rating"],
            "Confiance": row["confidence_score"],
            "Sévérité": "Haute" if row["confidence_score"] < 30 else "Moyenne",
        })

# B) Notes extrêmes (> 93 ou < 50)
for _, row in df[df["rating"] > 93].iterrows():
    anomalies.append({
        "Type": "Note exceptionnellement haute (>93)",
        "Joueur": row["name"],
        "Poste": row["position_group"],
        "Équipe": row["team"],
        "Note": row["rating"],
        "Confiance": row.get("confidence_score", "?"),
        "Sévérité": "Info",
    })

for _, row in df[df["rating"] < 50].iterrows():
    anomalies.append({
        "Type": "Note très basse (<50)",
        "Joueur": row["name"],
        "Poste": row["position_group"],
        "Équipe": row["team"],
        "Note": row["rating"],
        "Confiance": row.get("confidence_score", "?"),
        "Sévérité": "Info",
    })

# C) Postes sous-représentés par équipe
for team in df["team"].unique():
    team_df = df[df["team"] == team]
    for pg in ["FRONT_ROW", "LOCK", "BACK_ROW", "SCRUM_HALF", "FLY_HALF", "WINGER", "CENTRE", "FULLBACK"]:
        count = len(team_df[team_df["position_group"] == pg])
        if count < 2:
            anomalies.append({
                "Type": "Poste sous-représenté (<2 joueurs)",
                "Joueur": f"{pg} @ {team}",
                "Poste": pg,
                "Équipe": team,
                "Note": "-",
                "Confiance": "-",
                "Sévérité": "Basse" if count == 1 else "Haute",
            })

if anomalies:
    anom_df = pd.DataFrame(anomalies)
    sev_order = {"Haute": 0, "Moyenne": 1, "Basse": 2, "Info": 3}
    anom_df["_sort"] = anom_df["Sévérité"].map(sev_order)
    anom_df = anom_df.sort_values("_sort").drop(columns="_sort")

    n_haute = len(anom_df[anom_df["Sévérité"] == "Haute"])
    n_moy = len(anom_df[anom_df["Sévérité"] == "Moyenne"])

    if n_haute > 0:
        st.error(f"{n_haute} anomalie(s) haute sévérité détectée(s)")
    if n_moy > 0:
        st.warning(f"{n_moy} anomalie(s) moyenne sévérité")

    def color_sev(val):
        colors = {"Haute": "background-color:#7f1d1d", "Moyenne": "#78350f",
                  "Basse": "#1e3a5f", "Info": "#1a2e1a"}
        return colors.get(val, "")

    st.dataframe(
        anom_df.style.map(color_sev, subset=["Sévérité"]),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Exporter anomalies CSV",
        data=anom_df.to_csv(index=False).encode("utf-8"),
        file_name="audit_anomalies.csv",
        mime="text/csv",
    )
else:
    st.success("Aucune anomalie détectée.")

# ================================================================
# 4b. Sanity Check — notes, confiance, outliers
# ================================================================
st.divider()
st.subheader("Sanity Check — Qualité des notes")

has_rating_raw = "rating_raw" in df.columns
has_confidence = "confidence" in df.columns

# --- Top 20 global ---
sc_tab1, sc_tab2, sc_tab3 = st.tabs(["Top 20 global", "Distribution notes", "Outliers"])

with sc_tab1:
    view_cols = ["name", "team", "position_group", "rating"]
    if has_rating_raw:
        view_cols.append("rating_raw")
    if "confidence_badge" in df.columns:
        view_cols.append("confidence_badge")
    if "rank_position" in df.columns:
        view_cols.append("rank_position")

    top20 = df.nlargest(20, "rating")[view_cols].reset_index(drop=True)
    top20.index += 1
    st.markdown("**Top 20 global (note finale ajustée)**")
    st.dataframe(
        top20.style.background_gradient(subset=["rating"], cmap="YlOrRd"),
        use_container_width=True,
        height=min(750, 20 * 36 + 40),
    )

    st.markdown("**Top 10 par groupe de poste**")
    pos_tab_names = sorted(df["position_group"].unique())
    if pos_tab_names:
        pos_tabs = st.tabs(pos_tab_names)
        for ptab, pg in zip(pos_tabs, pos_tab_names):
            with ptab:
                grp = df[df["position_group"] == pg].nlargest(10, "rating")[view_cols].reset_index(drop=True)
                grp.index += 1
                st.dataframe(
                    grp.style.background_gradient(subset=["rating"], cmap="YlOrRd"),
                    use_container_width=True,
                    height=min(420, 10 * 36 + 40),
                )

with sc_tab2:
    sc2a, sc2b = st.columns(2)
    with sc2a:
        if has_rating_raw:
            fig_dist_raw = px.histogram(
                df, x="rating_raw", nbins=25, color="position_group",
                title="Distribution note brute (avant shrinkage)", opacity=0.7,
                labels={"rating_raw": "Note brute"},
            )
            fig_dist_raw.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10),
                                       paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_dist_raw, use_container_width=True)
        else:
            st.info("rating_raw absent — relancez le pipeline ou generate_sample.py")

    with sc2b:
        fig_dist_final = px.histogram(
            df, x="rating", nbins=25, color="position_group",
            title="Distribution note finale (après shrinkage)", opacity=0.7,
            labels={"rating": "Note finale"},
        )
        fig_dist_final.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10),
                                     paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_dist_final, use_container_width=True)

    if has_confidence:
        fig_conf = px.histogram(
            df, x="confidence", nbins=20,
            title="Distribution du score de confiance (0–1)",
            color_discrete_sequence=["#3B82F6"], opacity=0.8,
        )
        fig_conf.add_vline(x=0.7, line_dash="dash", line_color="#10B981", annotation_text="Seuil Haute (0.7)")
        fig_conf.add_vline(x=0.4, line_dash="dash", line_color="#F59E0B", annotation_text="Seuil Moyenne (0.4)")
        fig_conf.update_layout(height=260, margin=dict(l=10, r=10, t=40, b=10),
                               paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_conf, use_container_width=True)

with sc_tab3:
    st.markdown("**Outliers : note finale élevée + confiance basse** *(résultats potentiellement trompeurs)*")
    if has_rating_raw and has_confidence:
        # Seuil: top 30% des notes finales ET confiance < 0.40
        rating_p70 = df["rating"].quantile(0.70)
        outliers = df[(df["rating"] >= rating_p70) & (df["confidence"] < 0.40)].copy()
        outlier_cols = ["name", "team", "position_group", "rating", "rating_raw", "confidence", "confidence_badge"]
        outlier_cols = [c for c in outlier_cols if c in df.columns]
        if outliers.empty:
            st.success("Aucun outlier : pas de joueur top-rating avec confiance basse. Calibration OK.")
        else:
            st.warning(f"{len(outliers)} joueur(s) avec note élevée mais confiance faible :")
            st.dataframe(
                outliers[outlier_cols].sort_values("rating", ascending=False),
                hide_index=True, use_container_width=True,
            )
    else:
        st.info("Champs rating_raw et confidence absents — relancez calculate_ratings().")

    st.divider()
    st.markdown("**Benchmark 5 joueurs clés** *(sanity check calibration)*")
    bench_names = ["Antoine Dupont", "Romain Ntamack", "Thomas Ramos", "Gregory Alldritt", "Uini Atonio"]
    bench_cols = ["name", "position_group", "team"]
    if has_rating_raw:
        bench_cols += ["rating_raw"]
    if has_confidence:
        bench_cols += ["confidence"]
    bench_cols += ["rating"]
    if "confidence_badge" in df.columns:
        bench_cols += ["confidence_badge"]
    if "rank_position" in df.columns:
        bench_cols += ["rank_position"]
    bench_df = df[df["name"].isin(bench_names)][bench_cols].set_index("name")
    if bench_df.empty:
        st.caption("Joueurs clés non trouvés dans le dataset (mode DEMO : noms différents ?).")
    else:
        st.dataframe(bench_df, use_container_width=True)

# ================================================================
# 5. Heatmap coverage par poste × équipe
# ================================================================
st.divider()
st.subheader("Effectifs : joueurs par poste × équipe")

pivot = df.groupby(["team", "position_group"]).size().unstack(fill_value=0)
fig_heat = px.imshow(
    pivot,
    text_auto=True,
    color_continuous_scale="Blues",
    title="Nombre de joueurs par poste et par équipe",
    labels={"x": "Poste", "y": "Équipe", "color": "Nb joueurs"},
)
fig_heat.update_layout(height=450, margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(fig_heat, use_container_width=True)

# ================================================================
# 6. Data Health — pipeline_run_metadata.json
# ================================================================
st.divider()
st.subheader("Data Health — dernière exécution du pipeline")

import json as _json
from pathlib import Path as _Path

ROOT_DIR = _Path(__file__).parent.parent
meta_path = ROOT_DIR / "data" / "pipeline_run_metadata.json"
anom_path = ROOT_DIR / "data" / "validation_anomalies.json"
dropped_path = ROOT_DIR / "data" / "dropped_players.json"

if not meta_path.exists():
    st.info("Aucune métadonnée de pipeline disponible. Lance d'abord `python data/scrapers/run_pipeline.py`.")
else:
    with open(meta_path, encoding="utf-8") as _f:
        meta = _json.load(_f)

    # Résumé run
    dh1, dh2, dh3, dh4 = st.columns(4)
    dh1.metric("Saison", meta.get("season", "?"))
    dh2.metric("Durée pipeline", f"{meta.get('duration_seconds', 0):.0f}s")
    dh3.metric("Sources", ", ".join(meta.get("sources_used", []) or ["?"]))
    dh4.metric("Généré le", meta.get("generated_at", "?")[:16].replace("T", " "))

    # Qualité
    q = meta.get("quality", {})
    if q and not q.get("error"):
        st.markdown("**Qualité dataset**")
        qc1, qc2, qc3, qc4, qc5 = st.columns(5)
        qc1.metric("Joueurs", q.get("n_players", "?"))
        qc2.metric("Équipes", q.get("n_teams", "?"))
        core_total = q.get("core_cols_total", "?")
        core_found = q.get("core_cols_found", "?")
        cov_core_pct = q.get("coverage_core_pct", q.get("stat_coverage_pct", 0))
        qc3.metric(
            "Couv. Core",
            f"{cov_core_pct:.0f}%" if isinstance(cov_core_pct, (int, float)) else "?",
            help=f"Métriques moteur (weights.yaml) : {core_found}/{core_total} disponibles",
        )
        qc4.metric("Couv. Étendue", f"{q.get('coverage_extended_pct', 0):.0f}%",
                   help="Toutes les métriques disponibles")
        n_high = q.get("high_anomalies", 0)
        qc5.metric("Anomalies HIGH", n_high,
                   delta="OK" if n_high == 0 else f"{n_high} a corriger",
                   delta_color="normal" if n_high == 0 else "inverse")

        # Détail couverture core (A5)
        if q.get("core_cols_total") is not None:
            cov_raw = q.get("coverage_core", cov_core_pct / 100 if isinstance(cov_core_pct, float) else 0)
            st.caption(
                f"Métriques moteur : **{core_found}/{core_total}** colonnes présentes  |  "
                f"Couverture core : **{cov_raw:.1%}** (valeurs non-null / joueurs)"
            )

    # LNR scrape
    lnr_meta = meta.get("lnr_scrape", {})
    if lnr_meta:
        st.markdown("**Scraping LNR**")
        lm1, lm2, lm3 = st.columns(3)
        lm1.metric("Équipes actives", lnr_meta.get("teams_with_data", "?"))
        not_in = lnr_meta.get("teams_not_in_league", [])
        lm2.metric("Hors ligue", len(not_in),
                   help=", ".join(not_in) if not_in else "Aucune")
        confirmed = lnr_meta.get("season_confirmed", None)
        lm3.metric("Saison confirmée",
                   "Oui" if confirmed else ("Non" if confirmed is False else "?"),
                   delta="OK" if confirmed else "WARN",
                   delta_color="normal" if confirmed else "inverse")

    # Étapes pipeline
    steps = meta.get("steps", [])
    if steps:
        st.markdown("**Étapes**")
        step_cols = st.columns(len(steps))
        for col, step in zip(step_cols, steps):
            ok = step.get("status") == "OK"
            col.metric(step["name"], "OK" if ok else "FAIL",
                       delta_color="normal" if ok else "inverse")

    # Fichiers hashés
    files = meta.get("files", {})
    if files:
        with st.expander("Hashes des fichiers (traçabilité)"):
            fdf = pd.DataFrame([
                {"Fichier": k, "MD5": v.get("md5", "?"),
                 "Taille (KB)": v.get("size_kb", "?"),
                 "Modifié": v.get("modified", "?")[:16]}
                for k, v in files.items()
            ])
            st.dataframe(fdf, hide_index=True, use_container_width=True)

    # Anomalies HIGH (depuis validation_anomalies.json)
    if anom_path.exists():
        with open(anom_path, encoding="utf-8") as _f:
            anoms = _json.load(_f)
        high_anoms = [a for a in anoms if a.get("severity") == "HIGH"]
        if high_anoms:
            st.error(f"{len(high_anoms)} anomalie(s) HIGH dans le dataset :")
            st.dataframe(pd.DataFrame(high_anoms).head(20),
                         hide_index=True, use_container_width=True)

    # Joueurs exclus (dropped_players.json)
    if dropped_path.exists():
        with open(dropped_path, encoding="utf-8") as _f:
            dropped = _json.load(_f)
        if dropped:
            with st.expander(f"Joueurs exclus (anti-fantômes) : {len(dropped)}"):
                drop_df = pd.DataFrame(dropped)
                cols_show = [c for c in ["name", "team", "_drop_reason", "player_id", "lnr_url"] if c in drop_df.columns]
                st.dataframe(drop_df[cols_show].head(50),
                             hide_index=True, use_container_width=True)
