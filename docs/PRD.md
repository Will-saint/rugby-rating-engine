# PRD — Rugby Analytics Dashboard (Web)
**Version :** 1.0  
**Date :** 2026-04-30  
**Auteur :** Projet M2 PST&B  
**Statut :** Draft — prêt pour implémentation  

---

## 1. Contexte & Objectif

### 1.1 Contexte

Un moteur de notation rugby Python (Streamlit) existe et est pleinement opérationnel :
- **544 joueurs** scorés en 2025-2026, **6 saisons** historiques (2020–2026)
- **Moteur v6** : poids par poste, courbe d'âge, bonus international, gabarit 70/30
- Données sources : LNR public + Naim international ratings (1 195 joueurs, 20 nations)
- Tout le traitement est déjà fait — le MVP consiste à **exposer ces données via API** et à construire une **interface web professionnelle**

### 1.2 Objectif

Construire un dashboard web Next.js 14 qui consomme le moteur Python via FastAPI, destiné à :
1. **Mémoire M2 PST&B** — démonstration de data-driven decision making en rugby professionnel
2. **Démonstration clubs Pro** — outil de scouting / analyse tactique crédible

### 1.3 Non-objectifs (v1)

- Pas d'authentification complexe (une simple clé API suffit pour v1)
- Pas d'ingestion temps réel (les données sont batch, pipeline existant)
- Pas de rapport PDF auto-générés (phase 2)
- Pas de scraping dans l'API (le pipeline Python reste séparé)

---

## 2. Utilisateurs cibles

| Persona | Besoin principal | Fonctionnalité clé |
|---------|-----------------|-------------------|
| **Analyste club** | Évaluer un joueur cible rapidement | Profil joueur complet |
| **Entraîneur** | Comparer deux options à un poste | Comparateur côte-à-côte |
| **Directeur sportif** | Vision macro de son effectif | Dashboard équipe |
| **Étudiant / journaliste** | Vérifier pronostic avant un match | Prédicteur de match |
| **Jury de mémoire** | Comprendre la démarche data | Toutes les pages avec explications |

---

## 3. Architecture technique

### 3.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────┐
│  Next.js 14 (App Router)                                 │
│  TypeScript · Tailwind CSS · shadcn/ui                   │
│  Recharts (radar, line, bar) · React Query               │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP REST (JSON)
┌─────────────────▼───────────────────────────────────────┐
│  FastAPI (Python 3.14)                                   │
│  Lecture CSV → Pandas → JSON                             │
│  Cache in-memory (5 min TTL)                             │
│  CORS configuré pour Next.js                             │
└─────────────────┬───────────────────────────────────────┘
                  │ pd.read_csv()
┌─────────────────▼───────────────────────────────────────┐
│  data/seasons/<season>/players_scored.csv               │
│  6 saisons · 544 joueurs · 80 colonnes                  │
│  (moteur Python existant — inchangé)                     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Stack

| Composant | Technologie | Raison |
|-----------|-------------|--------|
| Frontend | Next.js 14 (App Router) | SSR/SSG, routing, image optimization |
| UI Components | shadcn/ui + Tailwind CSS v3 | Design system cohérent, rapide |
| Charts | Recharts | Radar, line chart, bar — léger, React-native |
| Data fetching | TanStack Query (React Query) | Cache client, loading states |
| Backend API | FastAPI (Python) | Réutilise l'écosystème Python existant |
| Data layer | Pandas + CSV | Moteur existant, pas de migration DB |
| Déploiement | Vercel (Next.js) + Railway (FastAPI) | Gratuit pour MVP |

### 3.3 Pourquoi pas de DB ?

Les CSV sont déjà structurés, optimisés, et régénérés par le pipeline. Une DB PostgreSQL serait utile si :
- On a >100k requêtes/jour (non applicable pour M2)
- On veut du temps réel (non applicable)

**En v1 : FastAPI lit les CSV avec Pandas, cache en mémoire 5 min.** Latence < 100ms.

---

## 4. API FastAPI — Endpoints

### Base URL : `http://localhost:8000/api/v1`

#### 4.1 Players

```
GET /players
  ?season=2025-2026 (default)
  ?position=SCRUM_HALF
  ?team=Toulouse
  ?min_rating=70
  ?limit=50&offset=0
  → PlayerSummary[]

GET /players/{lnr_slug}
  ?season=2025-2026
  → PlayerDetail (tous les champs + historique multi-saisons)

GET /players/{lnr_slug}/history
  → SeasonRating[] (rating par saison)

GET /players/search?q=Dupont
  → PlayerSummary[]
```

#### 4.2 Teams

```
GET /teams
  ?season=2025-2026
  → TeamSummary[] (team_rating, avg_rating, n_players)

GET /teams/{team_name}
  ?season=2025-2026
  → TeamDetail (roster par poste, axes agrégés, top 5)
```

#### 4.3 Match Predictor

```
POST /predict
  Body: { home: "Toulouse", away: "La Rochelle", season: "2025-2026" }
  → MatchPrediction { home_win_pct, away_win_pct, draw_pct, score_home, score_away, key_matchups[] }
```

#### 4.4 Leaderboard

```
GET /leaderboard
  ?season=2025-2026
  ?position=ALL
  ?team=ALL
  ?limit=100
  → PlayerRank[] (rank, name, team, position_group, rating, tier, age, nationality)
```

#### 4.5 Seasons & Meta

```
GET /seasons
  → string[] ["2020-2021", ..., "2025-2026"]

GET /meta
  → { n_players, n_teams, avg_rating, top_player, last_updated }
```

### 4.6 Types TypeScript (générés depuis l'API)

```typescript
interface PlayerSummary {
  lnr_slug: string
  name: string
  team: string
  position_group: string
  position_label: string
  rating: number
  tier: "LEGENDAIRE" | "OR" | "ARGENT" | "BRONZE" | "STANDARD"
  age: number | null
  height_cm: number | null
  weight_kg: number | null
  nationality: string | null
  photo_url: string | null
  confidence_badge: "Haute" | "Moyenne" | "Basse"
}

interface PlayerDetail extends PlayerSummary {
  rating_raw: number
  age_factor: number
  intl_bonus: number
  form_score: number
  form_trend: "↗" | "→" | "↘"
  axis_att: number    // Attaque / Franchissements
  axis_def: number    // Défense / Plaquages
  axis_ctrl: number   // Contrôle / Offloads
  axis_kick: number   // Jeu au pied
  axis_pow: number    // Puissance / Essais
  axis_gabarit: number // Physique (blend 70% poste + 30% global)
  axis_disc: number   // Discipline
  // International (si disponible)
  rating_intl: number | null
  matches_intl: number | null
  axis_course_intl: number | null
  axis_distrib_intl: number | null
  axis_kicking_intl: number | null
  // Historique
  history: SeasonRating[]
}

interface SeasonRating {
  season: string
  rating: number
  age: number | null
  matches_played: number
}
```

---

## 5. Modules Frontend — Spécifications détaillées

### MODULE 1 — Profil Joueur (`/player/[slug]`)

**Objectif :** Fiche complète d'un joueur, style scouting pro.

#### Layout

```
┌─────────────────────────────────────────────────────────┐
│  BANNER                                                  │
│  [Photo]  Prénom NOM          [TIER badge]               │
│           Poste · Club · Nationalité                     │
│           ★ 83.1  |  29 ans · 175cm · 85kg  |  FR       │
│           Forme ↗ · Confiance Haute · Rang #2 SCRUM_HALF │
└─────────────────────────────────────────────────────────┘

┌─────────────────┐  ┌──────────────────────────────────┐
│  RADAR 7 AXES   │  │  STATS CLÉS (6 métriques)        │
│  (Recharts)     │  │  Plaquages/80  Offloads  ...      │
│  T14 overlay    │  │                                   │
│  Intl overlay   │  │  ────────────────────────────     │
│  (si disponible)│  │  NOTES DÉTAIL                    │
│                 │  │  Note brute : 80.4               │
│                 │  │  + Courbe âge : +2.96 pts         │
│                 │  │  + Bonus intl : +1.84 pts         │
│                 │  │  + Forme : blend 20%              │
└─────────────────┘  └──────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  ÉVOLUTION DE LA NOTE (line chart — 6 saisons)          │
│  [2020-21] [2021-22] ... [2025-26]  avec tier zones     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  GABARIT vs poste (bar comparatif avec médiane poste)   │
└─────────────────────────────────────────────────────────┘
```

#### Radar axes (7)
`Attaque · Défense · Contrôle · Jeu au pied · Puissance · Physique · Discipline`

Si `rating_intl` disponible : double radar (T14 rouge + Intl bleu).

#### Acceptance criteria
- [ ] Page charge en < 1.5s (data via SSR ou React Query)
- [ ] Radar animé à l'entrée
- [ ] Section "Pourquoi cette note ?" expandable
- [ ] Responsive mobile (radar réduit, stats en colonne)
- [ ] Photo LNR chargée depuis `photo_url`, fallback avatar générique
- [ ] Lien "Comparer ce joueur" → Module 2

---

### MODULE 2 — Comparateur (`/compare`)

**Objectif :** Mettre deux joueurs côte à côte pour une décision de recrutement.

#### Layout

```
┌──────────────────────┬──────────────────────────────────┐
│  JOUEUR A            │  JOUEUR B                        │
│  [Mini carte]        │  [Mini carte]                    │
│  83.1 ARGENT         │  76.4 BRONZE                     │
├──────────────────────┴──────────────────────────────────┤
│           RADAR SUPERPOSÉ (deux tracés)                  │
│           Rouge = A    Bleu = B                          │
├─────────────────────────────────────────────────────────┤
│  TABLEAU COMPARATIF                                      │
│  Métrique       Joueur A    Joueur B    Gagnant          │
│  Plaquages/80     12.3       8.1          A ✓            │
│  Offloads/80       4.2       6.8          B ✓            │
│  Age              29 ans    26 ans        —              │
│  Physique          65        71           B ✓            │
│  Note finale      83.1      76.4          A ✓            │
├─────────────────────────────────────────────────────────┤
│  VERDICT IA (texte généré)                               │
│  "Dupont domine sur la défense (+52%) et l'attaque.      │
│   Couilloud a l'avantage physique pour son poste."       │
└─────────────────────────────────────────────────────────┘
```

#### Sélection joueurs
- Filtre poste → filtre équipe → liste triée par rating
- Toggle "même poste uniquement" (recommandé pour comparaison valide)
- URL shareable : `/compare?a=antoine-dupont&b=baptiste-couilloud`

#### Acceptance criteria
- [ ] Radar superposé avec légende et couleurs distinctes
- [ ] Tableau avec highlighting du gagnant par métrique
- [ ] Verdict textuel (template-based, pas GPT en v1)
- [ ] URL shareable
- [ ] Passage possible à 3 joueurs (toggle)

---

### MODULE 3 — Dashboard Équipe (`/team/[name]`)

**Objectif :** Vue macro d'un effectif Top 14 — pour un directeur sportif.

#### Layout

```
┌─────────────────────────────────────────────────────────┐
│  HEADER ÉQUIPE                                           │
│  [Logo]  Toulouse  · Top 14 2025-2026                   │
│  ★ 78.4 Force équipe  |  Rang #1  |  38 joueurs         │
└─────────────────────────────────────────────────────────┘

┌──────────────────────┬──────────────────────────────────┐
│  DISTRIBUTION NOTES  │  RADAR ÉQUIPE (6 axes moyens)    │
│  Histogramme         │                                  │
│  LEGENDAIRE: 0       │                                  │
│  OR: 3               │                                  │
│  ARGENT: 12  ████    │                                  │
│  BRONZE: 18  ██████  │                                  │
│  STANDARD: 5         │                                  │
└──────────────────────┴──────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  EFFECTIF PAR POSTE (8 colonnes accordéon)              │
│  ▼ SCRUM_HALF (3)     ▼ FLY_HALF (4)    ...            │
│    1. Dupont  83.1      1. Ntamack 79.8                 │
│    2. Blanc   71.2      2. Lesgourgues 68.4             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  ÉVOLUTION FORCE ÉQUIPE (line chart — 6 saisons)        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TOP 5 JOUEURS + ALERTES (basse confiance / forme ↘)    │
└─────────────────────────────────────────────────────────┘
```

#### Acceptance criteria
- [ ] Sélecteur équipe en haut (dropdown ou navigation)
- [ ] Chiffres mis en valeur (force équipe, rang)
- [ ] Effectif groupé par poste avec notation visuelle
- [ ] Évolution sur 6 saisons visible
- [ ] Alerte si joueur < 5 matchs (confiance basse)

---

### MODULE 4 — Prédicteur de match (`/predict`)

**Objectif :** Estimer la probabilité de victoire entre deux équipes.

#### Layout

```
┌──────────────────┬─────────────────┬──────────────────┐
│   Toulouse       │        VS       │   La Rochelle    │
│   [Sélecteur]    │                 │   [Sélecteur]    │
│   Force: 78.4    │                 │   Force: 75.1    │
└──────────────────┴─────────────────┴──────────────────┘

┌─────────────────────────────────────────────────────────┐
│                RÉSULTAT PRÉDICTION                       │
│                                                          │
│    Toulouse    ████████████████░░░░░░    La Rochelle    │
│      63%       win probability             37%          │
│                                                          │
│    Score estimé : 24 – 18                               │
│                                                          │
│    Confiance prédiction : ██████░░ Moyenne              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  MATCHUPS CLÉS (duels poste vs poste)                   │
│  SCRUM_HALF : Dupont 83.1 vs Hastoy 74.2  → Toulouse   │
│  LOCK       : Willemse 77 vs Skelton 81   → La Rochelle │
│  ...                                                     │
└─────────────────────────────────────────────────────────┘
```

#### Algorithme (réutilise engine/predictor.py via API)
Paramètres exposables : domicile/extérieur, ajustement forme.

#### Acceptance criteria
- [ ] Barre de probabilité animée
- [ ] Score estimé affiché
- [ ] Tableau matchups poste par poste
- [ ] Disclaimer "basé sur stats saison, sans facteur terrain"
- [ ] Shareable URL

---

### MODULE 5 — Classement général (`/leaderboard`)

**Objectif :** Leaderboard filtrable — vue d'ensemble du Top 14.

#### Layout

```
[Filtres] Saison ▾  Poste ▾  Équipe ▾  Note min ___  [Rechercher]

Rang  Joueur              Poste        Équipe     Note   Tier   Âge  Nat
 1    Antoine Dupont      SCRUM_HALF   Toulouse   83.1   ▪ARGENT  29  🇫🇷
 2    Matthieu Jalibert   FLY_HALF     Bordeaux   81.8   ▪ARGENT  27  🇫🇷
 3    ...

[Pagination 50 par page]
```

#### Podium Top 3 (visible uniquement sans filtre poste)
Affichage visuel Médaille Or/Argent/Bronze avec photo.

#### Acceptance criteria
- [ ] Tri par colonne (rating, âge, matchs)
- [ ] Filtre poste, équipe, note min, recherche nom
- [ ] Podium top 3 (quand pas de filtre poste)
- [ ] Lien vers profil joueur depuis chaque ligne
- [ ] Indicateur tier coloré

---

## 6. Design System

### 6.1 Palette (inspirée de la Streamlit app existante)

```css
--bg-primary:    #0B1220   /* fond principal */
--bg-card:       #111827   /* cartes */
--bg-elevated:   #1F2937   /* éléments surélevés */
--border:        rgba(255,255,255,0.08)

--orange:        #F97316   /* accent principal */
--orange-light:  #FBBF24   /* titres gradient */
--green:         #10B981   /* positif, forme ↗ */
--red:           #EF4444   /* négatif, forme ↘ */
--blue:          #3B82F6   /* info, sélection */
--purple:        #8B5CF6   /* international */

/* Tiers */
--tier-legendaire: #FFD700
--tier-or:         #C8A840
--tier-argent:     #10B981
--tier-bronze:     #F97316
--tier-standard:   #6B7280
```

### 6.2 Typographie
- Headings : `Rajdhani` (Google Fonts) — style rugby/sport
- Body : `Inter`
- Monospace (stats) : `JetBrains Mono`

### 6.3 Composants shadcn/ui utilisés
`Card`, `Badge`, `Table`, `Select`, `Input`, `Tabs`, `Progress`, `Skeleton`, `Tooltip`

---

## 7. Structure projet Next.js

```
apps/web/
├── app/
│   ├── layout.tsx                  # RootLayout + Navbar + fonts
│   ├── page.tsx                    # Landing / accueil
│   ├── player/
│   │   └── [slug]/page.tsx         # Module 1 — Profil joueur
│   ├── compare/
│   │   └── page.tsx                # Module 2 — Comparateur
│   ├── team/
│   │   └── [name]/page.tsx         # Module 3 — Dashboard équipe
│   ├── predict/
│   │   └── page.tsx                # Module 4 — Prédicteur
│   └── leaderboard/
│       └── page.tsx                # Module 5 — Classement
├── components/
│   ├── player/
│   │   ├── PlayerBanner.tsx        # Header avec photo + note
│   │   ├── PlayerRadar.tsx         # Radar 7 axes (Recharts)
│   │   ├── PlayerStatsGrid.tsx     # 6 métriques clés
│   │   ├── PlayerHistory.tsx       # Line chart évolution
│   │   └── PlayerCard.tsx          # Mini carte pour listes
│   ├── team/
│   │   ├── TeamHeader.tsx
│   │   ├── TeamRoster.tsx
│   │   └── TeamRadar.tsx
│   ├── compare/
│   │   ├── CompareRadar.tsx        # Radar superposé
│   │   └── CompareTable.tsx        # Tableau métriques
│   ├── predict/
│   │   ├── PredictForm.tsx
│   │   └── PredictResult.tsx
│   ├── leaderboard/
│   │   ├── LeaderboardTable.tsx
│   │   └── LeaderboardPodium.tsx
│   └── ui/                         # shadcn/ui components
├── lib/
│   ├── api.ts                      # fetch wrappers → FastAPI
│   ├── types.ts                    # TypeScript interfaces
│   └── utils.ts                    # tier colors, formatters
└── hooks/
    ├── usePlayers.ts
    ├── usePlayer.ts
    └── useTeam.ts
```

---

## 8. Structure projet FastAPI

```
apps/api/
├── main.py                  # FastAPI app + CORS + router registration
├── routers/
│   ├── players.py           # GET /players, /players/{slug}
│   ├── teams.py             # GET /teams, /teams/{name}
│   ├── leaderboard.py       # GET /leaderboard
│   ├── predict.py           # POST /predict
│   └── meta.py              # GET /seasons, /meta
├── services/
│   ├── data_loader.py       # Pandas CSV loader + in-memory cache
│   ├── predictor.py         # Wrapper engine/predictor.py
│   └── history.py           # Multi-season aggregation
└── schemas/
    ├── player.py            # Pydantic PlayerSummary, PlayerDetail
    ├── team.py              # TeamSummary, TeamDetail
    └── predict.py           # MatchPrediction
```

---

## 9. Plan d'implémentation (ordre recommandé)

### Phase 1 — Infrastructure (1–2 jours)
- [ ] Créer `apps/api/` FastAPI avec `data_loader.py` (CSV → Pandas → JSON)
- [ ] Implémenter `/players`, `/teams`, `/seasons`, `/meta`
- [ ] Tester tous les endpoints avec données 2025-2026
- [ ] Créer `apps/web/` Next.js 14 avec Tailwind + shadcn/ui
- [ ] Implémenter `lib/api.ts` + types TypeScript
- [ ] Page landing minimaliste avec KPIs globaux

### Phase 2 — Module 5 : Leaderboard (1 jour)
- [ ] `GET /leaderboard` avec filtres
- [ ] `LeaderboardTable` + tri colonnes
- [ ] Podium top 3
- [ ] Filtres poste/équipe/note

### Phase 3 — Module 1 : Profil joueur (2 jours)
- [ ] `GET /players/{slug}` + historique multi-saisons
- [ ] `PlayerBanner` (photo, note, tier, physique)
- [ ] `PlayerRadar` (7 axes, animation)
- [ ] `PlayerHistory` (line chart 6 saisons)
- [ ] Section "Pourquoi cette note?"

### Phase 4 — Module 3 : Dashboard équipe (1 jour)
- [ ] `GET /teams/{name}`
- [ ] `TeamRoster` par poste
- [ ] Histogramme distribution
- [ ] Évolution force sur 6 saisons

### Phase 5 — Module 2 : Comparateur (1 jour)
- [ ] `CompareRadar` (superposition)
- [ ] `CompareTable` avec winner highlighting
- [ ] URL shareable

### Phase 6 — Module 4 : Prédicteur (1 jour)
- [ ] `POST /predict`
- [ ] `PredictResult` avec barre animée
- [ ] Tableau matchups

### Phase 7 — Polish (1–2 jours)
- [ ] Responsive mobile sur tous les modules
- [ ] Loading skeletons
- [ ] Error boundaries
- [ ] SEO meta tags (pour le mémoire)
- [ ] Déploiement Vercel + Railway

---

## 10. Métriques de succès (mémoire M2)

| Métrique | Cible |
|----------|-------|
| Couverture fonctionnelle | 5/5 modules opérationnels |
| Latence API p95 | < 200ms |
| Données affichées | 544 joueurs, 6 saisons, 14 équipes |
| Mobile responsive | Toutes les pages |
| Précision prédicteur | Validée sur historique saisons passées |
| Uptime demo | 99% pendant la soutenance |

---

## 11. Points d'attention pour la soutenance M2

1. **Expliquer le moteur de notation** — la fiche joueur contient une section "Pourquoi cette note?" qui décompose chaque contribution (stats + âge + international + forme)
2. **Montrer la valeur des 6 saisons** — l'évolution temporelle démontre le caractère prédictif de la donnée
3. **Cas Dupont** — illustration du problème "peu de matchs T14, star internationale" et comment la reputation anchor le résout
4. **Gabarit position-relative** — montrer que 175cm est bon pour un 9, pas pour un pilier
5. **Comparateur = outil de recrutement** — scénario concret "Toulouse cherche un 9, compare Dupont vs Couilloud"
