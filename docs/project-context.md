# Rugby Rating Engine — Project Context (BMAD)

> Generated: 2026-04-29 | Season: 2025-2026 | Players: 544 | Seasons: 6 (2020–2026)

---

## 1. Project Overview

**Rugby Rating Engine** is a Streamlit data application that rates every Top 14 rugby player on a FIFA-style 40–99 scale. It ingests public LNR data, enriches it with Statbunker stats and Naim international ratings, then outputs per-player ratings with 6 visual axes, physical profiles, form curves, and historical evolution.

**Primary users:** scouts, coaches, analysts, fans.
**Source of truth for all data:** `data/seasons/<season>/players_scored.csv`

---

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit (Python) |
| Rating engine | Pure Python + Pandas + NumPy |
| Data scraping | requests + BeautifulSoup (LNR, Statbunker, ESPN) |
| Data storage | CSV files (no database) |
| Visualisation | Plotly Express + Plotly Graph Objects |
| Photo cache | Local disk (`data/raw/photos/`) |
| Config | `config/` YAML files |

---

## 3. Directory Structure

```
rugby-rating-engine/
├── Home.py                        # Streamlit entry point (accueil + KPIs)
├── utils.py                       # load_data(), rating_to_tier(), AXIS_COLORS…
├── pages/
│   ├── 1_Player_Cards.py          # Carte FIFA par joueur (banner, radar, axes)
│   ├── 2_Leaderboard.py           # Classement global + podium top 3
│   ├── 3_Comparator.py            # Comparateur 2–3 joueurs (radar overlay)
│   ├── 4_Team_Strength.py         # Force par équipe
│   ├── 5_Match_Predictor.py       # Prédicteur de match (probabilité victoire)
│   ├── 6_Audit_Qualite.py         # Audit couverture données + anomalies
│   ├── 7_Club_Stats.py            # Stats par club
│   ├── 8_Season_History.py        # Évolution joueur/équipe sur 6 saisons
│   ├── 9_International.py         # Classements internationaux (Naim)
│   └── 10_Selections.py           # Sélections nationales
├── engine/
│   ├── ratings.py                 # ★ Moteur de notation principal
│   ├── form.py                    # Forme récente (5 derniers matchs, decay 0.7)
│   ├── merge_intl.py              # Fusion données internationales Naim
│   ├── predictor.py               # Algorithme prédiction match
│   ├── card.py                    # Rendu carte FIFA HTML
│   ├── position_audit.py          # Détection mauvais postes
│   ├── scouting_card.py           # Export fiche scouting PDF
│   └── scouting_export.py         # Export CSV scouting
├── data/
│   ├── players.csv                # Dataset courant (sans ratings)
│   ├── players_scored.csv         # Dataset courant (avec ratings) — symlink saison courante
│   ├── international_ratings.csv  # Ratings Naim (1195 joueurs, 20 nations)
│   ├── player_form.csv            # Forme pré-calculée
│   ├── players_all_seasons.csv    # Consolidé multi-saisons (généré par combine_seasons.py)
│   ├── raw/
│   │   ├── players_merged.json    # ★ Source profils physiques (age/height/weight)
│   │   ├── lnr_raw.json           # Données LNR brutes (saison courante)
│   │   ├── lnr_match_history.json # Historique matchs (forme)
│   │   └── photos/                # Cache photos joueurs
│   └── seasons/
│       ├── 2020-2021/             # players.csv + players_scored.csv + lnr_raw.json
│       ├── 2021-2022/
│       ├── 2022-2023/
│       ├── 2023-2024/
│       ├── 2024-2025/
│       └── 2025-2026/             # Saison courante (544 joueurs)
└── data/scrapers/
    ├── run_pipeline.py            # ★ Pipeline complet (scrape → normalise → score)
    ├── scraper_lnr.py             # Scraper LNR (roster, stats, profils)
    ├── scraper_statbunker.py      # Scraper Statbunker (stats avancées)
    ├── enrich_profiles.py         # Enrichissement profils physiques (LNR profile pages)
    ├── normalize.py               # Normalisation + déduplication + /80
    ├── compute_form.py            # Calcul forme récente
    └── combine_seasons.py         # Consolidation multi-saisons
```

---

## 4. Rating Pipeline (engine/ratings.py)

### 4.1 Steps (calculate_ratings)

```
Input: players.csv (raw stats)
  │
  ├─ 0. Position overrides (POSITION_OVERRIDES dict — slug-based corrections)
  ├─ 0b. Global height/weight normalization (for gabarit blend 70/30)
  │
  ├─ Per position group loop (8 groups):
  │   ├─ 1. kick_points_per80 = max(points - tries*5, 0)
  │   ├─ 2. Min-max [p5,p95] normalization per metric per position
  │   │      Bonus metrics (floor at 50, no penalty):
  │   │        SCRUM_HALF, WINGER, BACK_ROW, CENTRE → kick_points_per80
  │   ├─ 3. score_raw = Σ(metric_norm * weight)  [0–100]
  │   ├─ 4. confidence = step fn (≥600min→1.0, ≥300→0.75, ≥150→0.60, else→0.50)
  │   ├─ 5. score_final = conf * score_raw + (1-conf) * 50  (shrinkage)
  │   ├─ 6. rating_raw = clip(40 + 0.6*score_raw, 40, 99)
  │   │    rating     = clip(40 + 0.6*score_final, 40, 99)
  │   └─ 7. Visual axes (0–100, independent of score):
  │          axis_att=line_breaks, axis_def=tackles, axis_ctrl=offloads,
  │          axis_kick=kick_points, axis_pow=0.6*tries+0.4*turnovers
  │          axis_gabarit = 70%*pos_norm + 30%*global_norm  (blend taille/poids)
  │
  ├─ 7b. Form blend: rating = 0.80*rating + 0.20*form_score→FIFA_scale
  ├─ 8.  Discipline malus: YC -2, OC -3, RC -8 (cap -10)
  ├─ 8.5 Age curve: Gaussian peak 28.5 ans, ±3 pts max
  ├─ 9.  Metadata (labels, confidence_badge, rank_position, percentile)
  ├─ 10. enrich_with_intl (merge rating_intl, axes_intl depuis Naim)
  ├─ 11. Reputation anchor: si conf<1.0 et rating_intl disponible →
  │       floor = rating_intl * (0.85 + 0.05*(1-conf))  [boost only]
  └─ 12. International bonus: +0 à +2.5 pts pour tous les capés
          bonus = ((rating_intl - 75) / 25 * 2.5).clip(0, 2.5)

Output: players_scored.csv (80+ colonnes)
```

### 4.2 Rating Scale (Tiers)

| Tier | Range | Couleur |
|------|-------|---------|
| LEGENDAIRE | ≥ 90 | Or #FFD700 |
| OR | 84–89 | Ambre #C8A840 |
| ARGENT | 77–83 | Vert #3A7A28 |
| BRONZE | 70–76 | Orange #8C4020 |
| STANDARD | < 70 | Gris #585858 |

### 4.3 Position Weights (NAIM_POS_WEIGHTS)

```
FRONT_ROW : tackles 35%, turnovers 20%, weight_kg 25%, offloads 10%, …
LOCK       : tackles 40%, turnovers 20%, height_cm 20%, …
BACK_ROW   : tackles 30%, turnovers 30%, offloads 15%, …
SCRUM_HALF : offloads 35%, turnovers 20%, tackles 15%, tries 10%, …
FLY_HALF   : offloads 25%, kick_pts 15%, line_breaks 15%, tries 15%, …
WINGER     : line_breaks 40%, tries 15%, offloads 15%, …
CENTRE     : line_breaks 25%, offloads 20%, tackles 20%, …
FULLBACK   : kick_pts 20%, line_breaks 20%, tries 15%, offloads 15%, …
```

### 4.4 Gabarit Blend (axis_gabarit)

Physical axis = **70% position-relative** (vs peers at same position) + **30% global** (vs all 544 players).

Per-position height/weight weights (`_GABARIT_BLEND`):
- FRONT_ROW: 20% height + 80% weight (masse prime)
- LOCK: 85% height + 15% weight (taille prime)
- BACK_ROW: 35% height + 65% weight
- SCRUM_HALF: 40% height + 60% weight
- FLY_HALF: 65% height + 35% weight
- WINGER: 35% height + 65% weight
- CENTRE: 30% height + 70% weight
- FULLBACK: 65% height + 35% weight

---

## 5. Data Pipeline (run_pipeline.py)

```bash
# Full pipeline (scrape + score)
python data/scrapers/run_pipeline.py --season 2025-2026

# Skip scraping (just re-score existing data)
python data/scrapers/run_pipeline.py --skip-scraping

# Score a specific season
python -c "from data.scrapers.run_pipeline import step_score; step_score('2023-2024')"
```

### Pipeline steps
1. **LNR scraping** — roster + stats (top14.lnr.fr)
2. **Statbunker** — advanced stats complement
3. **enrich_profiles** — age/height/weight from LNR profile pages
4. **normalize** — dedup, /80 per minute, validation
5. **form** — compute_form.py (5-match window, decay 0.7)
6. **step_score** — calculate_ratings() + sync to seasons/
   - Injects physical profiles from `data/raw/players_merged.json`
   - Adjusts age by season (current_year - season_start offset)
7. **regression check** — validates player counts, coverage, anomalies

### Profile data flow
```
enrich_profiles.py → data/raw/players_merged.json  (540 players, 91–97% coverage)
                      ↓ (injected by step_score per season)
data/seasons/<season>/players.csv  (stats only)
                      ↓ merge on lnr_slug
data/seasons/<season>/players_scored.csv  (stats + profiles + ratings)
```

---

## 6. Key Data Files

| File | Description | Rows |
|------|-------------|------|
| `data/seasons/2025-2026/players_scored.csv` | Saison courante, scored | 544 |
| `data/raw/players_merged.json` | Profils physiques enrichis | 540 |
| `data/raw/lnr_match_history.json` | Matchs j1-j18 (forme) | ~8000 player-match |
| `data/international_ratings.csv` | Ratings Naim ESPN 2016-2024 | 1195 |
| `data/player_form.csv` | Forme pré-calculée | 534 |

---

## 7. Key Columns in players_scored.csv

### Identity
`player_id`, `lnr_slug`, `name`, `team`, `position_group`, `season`

### Physical profile (from players_merged.json)
`age`, `height_cm`, `weight_kg`, `nationality`

### Raw stats (/80 min)
`tackles_per80`, `turnovers_won_per80`, `line_breaks_per80`, `offloads_per80`,
`kick_points_per80`, `tries_per80`, `points_scored_per80`

### Ratings
`rating_raw` (pure performance), `rating` (final after all adjustments),
`confidence` (0.50–1.00), `age_factor` (±3 pts), `intl_bonus` (0–2.5 pts)

### Visual axes (0–100)
`axis_att`, `axis_def`, `axis_ctrl`, `axis_kick`, `axis_pow`, `axis_gabarit`, `axis_disc`

### Form
`form_score` (0–100), `form_trend` (↗/→/↘), `form_matches`

### International (Naim)
`rating_intl`, `team_intl`, `matches_intl`,
`axis_course_intl`, `axis_distrib_intl`, `axis_kicking_intl`,
`axis_physique_intl`, `axis_rigueur_intl`, `axis_danger_intl`, `axis_melee_intl`

---

## 8. Multi-Season Architecture

6 seasons available: **2020-2021 → 2025-2026**

Each season has its own `data/seasons/<season>/players_scored.csv`.
`utils.py::load_data(season)` reads the correct season file with mtime-based cache invalidation.

Age is adjusted per season: player aged 29 in 2025-2026 → aged 27 in 2023-2024.
Physical profiles are always sourced from `players_merged.json` (current values, best available).

---

## 9. Important Constraints & Known Quirks

- **LNR public stats (100% coverage):** tackles, offloads, line_breaks, turnovers_won, points_scored/tries, discipline cards
- **Paywall stats (0% coverage):** carries, meters, passes, kick_meters, penalties, ruck_arrivals, lineout_wins, scrum_success
- **Bonus-only metrics:** `kick_points_per80` for SCRUM_HALF, WINGER, BACK_ROW, CENTRE — floored at 50 (no penalty for non-kickers)
- **Position overrides:** `POSITION_OVERRIDES` in ratings.py corrects LNR misclassifications (e.g. Bielle-Biarrey → WINGER)
- **Streamlit cache:** uses `_mtime` parameter trick to auto-invalidate when CSV changes
- **No SQLite/DB:** all persistence is CSV. No runtime DB queries.
- **Python version:** uses py -3.14 (system default in MinGW is 3.12, use `py -3.14` for this project)

---

## 10. Running the App

```bash
cd C:\Users\pc\rugby-platform\app1-rating-engine\rugby-rating-engine
streamlit run Home.py
```

Pages auto-discovered from `pages/` by Streamlit multipage convention.

---

## 11. Current Season Stats (2025-2026)

- **Players:** 544 (14 équipes, 8 groupes de poste)
- **Rating range:** 41.3 – 86.0 (moyenne 65.1)
- **Age coverage:** 534/544 (98%)
- **Height coverage:** 487/544 (89%)
- **Weight coverage:** 521/544 (96%)
- **International data:** 120 joueurs avec rating_intl
- **Form data:** 531 joueurs avec form_score
