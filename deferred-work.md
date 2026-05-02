# Deferred Work — Rugby Rating Engine

## ESPN / Stats paywall (bloqué réseau)

**Date :** 2026-05-02  
**Priorité :** HAUTE — Débloque carries, meters, passes, kick_meters (0% couverture)

### Scraper ESPN
- Fichier : `data/scrapers/scraper_espn.py`
- Commande : `py -3.14 data/scrapers/scraper_espn.py --season 2025-2026 --enrich-csv`
- Statut : HTTP 400 depuis cet environnement (API ESPN bloquée)
- URLs à tester manuellement :
  - `https://site.api.espn.com/apis/site/v2/sports/rugby/23/statistics?limit=500&season=2025&seasontype=2`
  - Rugbypass fallback : `https://www.rugbypass.com/super-rugby/stats/players/?competition=top-14&season=2025&stat=metres-gained`

### Impact si débloqué
Stats récupérables : `carries_per80`, `meters_per80`, `kick_meters_per80`  
Stats manquantes restantes (paywall dur LNR) : `passes_per80`, `penalties_per80`, `ruck_arrivals_per80`, `lineout_wins_per80`, `scrum_success_pct`

### Après déblocage
1. Lancer le scraper ESPN
2. Vérifier couverture : `py -3.14 -c "import pandas as pd; df=pd.read_csv('data/players_scored.csv'); [print(c, df[c].notna().sum()) for c in ['carries_per80','meters_per80','passes_per80']]"`
3. Relancer le pipeline : `py -3.14 data/scrapers/run_pipeline.py --skip-scraping --season 2025-2026`
4. Recalibrer les poids si nécessaire (carries/meters = indicateurs clés pour BACK_ROW, CENTRE)

### L'Équipe scraper
- À créer : `data/scrapers/scraper_lequipe.py`
- Source potentielle : lequipe.fr/Rugby/Top-14/stats
- Même stats cibles que ESPN
