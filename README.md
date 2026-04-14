# Rugby Rating Engine

A data-driven rating system for Top 14 rugby players, built with Streamlit.

## What it does

- **Player Cards** — detailed rating profile for each player across 7 performance axes (Attack, Defense, Discipline, Control, Kick, Power, Form)
- **Leaderboard** — full player rankings filtered by position, team, and season
- **Comparator** — side-by-side comparison of any two players with radar charts
- **Team Strength** — club-level aggregated ratings and squad depth analysis
- **Match Predictor** — win probability model based on squad ratings and head-to-head history
- **Season History** — rating evolution across multiple Top 14 seasons
- **International** — cross-league comparison merging Top 14 and international data
- **Selections** — optimal XV builder by position group

## Data

- Source: LNR (top14.lnr.fr) public stats — 550 players, 2025-2026 season
- Rating engine: 7-axis Naim model, position-normalized
- Coverage: 100% for LNR public stats (tackles, offloads, line breaks, turnovers, points)

## Run locally

```bash
pip install -r requirements.txt
streamlit run Home.py
```

## Stack

- Python 3.10+
- Streamlit 1.32+
- Pandas, Plotly, NumPy, SciPy
- BeautifulSoup4 (data pipeline)
