# Live football data sources — research notes

Written 2026-09-11. Every endpoint below was called live on that date; the
responses quoted are real. Season in progress: **Premier League 2026/27**,
3 gameweeks played, GW4 deadline 2026-09-12 12:30 UTC.

The existing project runs on **StatsBomb open data**, which is event-level and
free but *not* current: its only Premier League seasons are **2015/16 and
2003/04** (24 competitions total). For anything about this season we need a
different source.

---

## The shortlist

| Source | Key? | Cost | What it gives us | Verdict |
|---|---|---|---|---|
| **Understat** | no | free | xG/xA per team, per player, **per shot** (x, y, situation, body part) | **Primary.** The only free source of shot-level xG for the current season. |
| **Fantasy PL API** | no | free | Every PL player: minutes, goals, xG/xA/xGI/xGC, per-90s, price, ownership, injury news, set-piece order | **Primary.** Official Opta-derived numbers, updated nightly. |
| **ESPN hidden API** | no | free | Fixtures, live scores, league table | Useful for the table and the schedule. |
| **TheSportsDB** | test key `3` | free | Table, badges, logos, team metadata | Good for crests/branding only. |
| **football-data.org** | yes | free tier | Matches, standings, scorers, referees, crests, stable ids | **Primary spine.** 10 req/min, current season. No xG, no lineups. |
| **API-Football** | yes | free 100 req/day | Lineups w/ grid, events, fixture + player stats, odds, predictions | **Free plan caps at seasons 2022-2024** — cannot see 2026/27. Backtests only. |
| **FBref** | — | free | Deep Opta tables | **Blocked** — returns Cloudflare "Just a moment…" (403). Don't build on it. |

---

## 1. Understat — the xG engine

No key, no registration. Three endpoints, all discovered by reading
`understat.com/js/*.min.js`. **Note:** the old scraping pattern every tutorial
and the `understat` PyPI package still uses — regex `JSON.parse('...')` out of
the HTML — is **dead**. The pages now load their data over AJAX. Use these:

```
GET https://understat.com/main/getLeagueData/EPL/2026     # whole season, one call
GET https://understat.com/main/getMatchData/{match_id}    # shots + rosters
    https://understat.com/main/getPlayersStats/  (POST league=EPL&season=2026)
```

Send `X-Requested-With: XMLHttpRequest` and a browser `User-Agent`. Responses
are **gzip-encoded** and `requests` handles that transparently; raw `curl`
does not.

### `getLeagueData/EPL/2026` — 33 KB, the entire season

```
{ "teams": {20 teams}, "players": [387], "dates": [380 fixtures] }
```

A fixture (`dates[]`) — note it carries xG *and* a win/draw/loss forecast:

```json
{"id": "31209", "isResult": true,
 "h": {"id": "83", "title": "Arsenal",  "short_title": "ARS"},
 "a": {"id": "80", "title": "Chelsea",  "short_title": "CHE"},
 "goals": {"h": "2", "a": "1"},
 "xG":    {"h": "2.80555", "a": "0.430508"},
 "datetime": "2026-09-06 15:30:00",
 "forecast": {"w": "0.9066", "d": "0.0737", "l": "0.0197"}}
```

A team's per-match row (`teams[id].history[]`) — the advanced-metric payload:

```json
{"h_a": "a", "xG": 0.275, "xGA": 4.003, "npxG": 0.275, "npxGA": 4.003,
 "ppda": {"att": 355, "def": 11}, "ppda_allowed": {"att": 127, "def": 34},
 "deep": 0, "deep_allowed": 13, "scored": 0, "missed": 4,
 "xpts": 0.0108, "result": "l", "date": "2026-08-23 13:00:00",
 "wins": 0, "draws": 0, "loses": 1, "pts": 0, "npxGD": -3.728}
```

- **npxG** — xG with penalties stripped out. The honest attacking number.
- **PPDA** — opposition passes allowed per defensive action. Low = high press.
  Divide `att / def`. Brighton are on 4.1, Aston Villa on 20.3.
- **deep** — completed passes within 20 yards of goal. Territory, not chances.
- **xpts** — points the xG says you *deserved*. The gap to real points is luck,
  finishing, or goalkeeping, and it mostly closes over a season.

A player row (`players[]`, 387 of them):

```json
{"id": "1228", "player_name": "Bruno Fernandes", "games": "3", "time": "270",
 "goals": "3", "xG": "2.3776", "assists": "1", "xA": "0.6804",
 "shots": "15", "key_passes": "8", "position": "M", "team_title": "Manchester United",
 "npg": "2", "npxG": "1.6164", "xGChain": "3.7040", "xGBuildup": "2.1390"}
```

- **xGChain** — total xG of every possession the player touched.
- **xGBuildup** — the same, minus the shot and the assist. Credits the deep-lying
  players who never appear in a goals-and-assists table.

### `getMatchData/{id}` — shot level, and this is the good stuff

```json
{"id": "693065", "minute": "24", "result": "Goal",
 "X": "0.8230", "Y": "0.3340", "xG": "0.03537",
 "player": "Kai Havertz", "player_id": "5220", "h_a": "h",
 "situation": "OpenPlay", "shotType": "LeftFoot",
 "player_assisted": "Declan Rice", "lastAction": "Pass",
 "h_team": "Arsenal", "a_team": "Chelsea", "date": "2026-09-06 15:30:00"}
```

Coordinates are **normalised 0–1** on a pitch the shooter always attacks
left → right — the same convention StatsBomb uses, just scaled. To reuse
`src/statsbomb.py`'s plotting path: `x = X * 120`, `y = Y * 80`.

`rosters` in the same response gives every player's minutes, shots, xG, xA,
xGChain, xGBuildup and position for that match.

## 2. Fantasy Premier League API — official, and richer than it sounds

No key. `https://fantasy.premierleague.com/api/`

| Endpoint | Contents |
|---|---|
| `bootstrap-static/` | 1.7 MB: 656 players, 20 teams, 38 gameweeks, stat dictionary |
| `fixtures/` | all 380 fixtures + per-match goal/assist/card/BPS breakdowns by player |
| `element-summary/{id}/` | one player's full gameweek-by-gameweek history |

A player object carries ~110 fields. The analytically interesting ones are
Opta-derived and were *not* in this API a few seasons ago:

```
expected_goals  expected_assists  expected_goal_involvements  expected_goals_conceded
expected_goals_per_90  expected_assists_per_90  expected_goal_involvements_per_90
minutes goals_scored assists clean_sheets saves starts
tackles recoveries clearances_blocks_interceptions defensive_contribution
influence creativity threat ict_index  (+ _rank and _rank_type for each)
```

Plus things no stats API gives you:

```
now_cost 72              price in £0.1m
selected_by_percent      ownership across 10,688,716 managers
form "9.3"  ep_next "7.0"
status "d"  news "Thigh injury - 75% chance of playing"  chance_of_playing_next_round 75
penalties_order 3  corners_and_indirect_freekicks_order 2   set-piece hierarchy
```

`fixtures/` is the cheap way to get a match's key events without scraping:

```json
{"code": 2645215, "event": 3, "finished": true, "kickoff_time": "2026-09-06T15:30:00Z",
 "team_h": 1, "team_a": 6, "team_h_score": 2, "team_a_score": 1,
 "stats": [{"identifier": "goals_scored",
            "h": [{"value": 1, "element": 15}, {"value": 1, "element": 26}],
            "a": [{"value": 1, "element": 40}]}, ...]}
```

`element` is an FPL player id; `team_h`/`team_a` index `bootstrap-static.teams`.

## 3. ESPN hidden API — table and schedule

No key, no docs, no stability guarantee. Verified working:

```
https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard
https://site.web.api.espn.com/apis/v2/sports/soccer/eng.1/standings?season=2026
```

The scoreboard returns fixtures with venue, broadcast, status and competitors;
standings returns 20 entries each with `gamesPlayed, wins, ties, losses,
pointsFor, pointsAgainst, pointDifferential, points, rank, rankChange`.

Caveats found in testing: `site.api…/standings` 403s (use `site.web.api`), and
the `?dates=YYYYMMDD` scoreboard filter 403'd intermittently. Treat as
best-effort, with a cached fallback.

## 4. Keyed APIs — both keys tested 2026-09-11

Credentials live in `.env` (gitignored; `.env.example` shows the shape).

### football-data.org — works on this season

`X-Auth-Token` header, `https://api.football-data.org/v4/`. Rate limit comes
back in a response header: `x-requests-available-minute: 9`, so **10/min**.

Verified live: `competitions/PL/standings` (matchday 4, 2026-08-21 -> 2027-05-30),
`competitions/PL/matches?matchday=3`, `competitions/PL/scorers`, `matches/{id}`.

```json
{"position": 1,
 "team": {"id": 65, "name": "Manchester City FC", "shortName": "Man City",
          "tla": "MCI", "crest": "https://crests.football-data.org/65.png"},
 "playedGames": 3, "won": 3, "draw": 0, "lost": 0,
 "points": 9, "goalsFor": 7, "goalsAgainst": 2, "goalDifference": 5}
```

A match carries clean metadata the free scrapers don't have — **venue, referee,
half-time score, official crests, canonical team ids**:

```json
{"id": 560566, "utcDate": "2026-09-04T19:00:00Z", "status": "FINISHED", "matchday": 3,
 "homeTeam": {"id": 349, "name": "Ipswich Town FC", "tla": "IPS", "crest": "..."},
 "awayTeam": {"id": 64,  "name": "Liverpool FC",   "tla": "LIV", "crest": "..."},
 "score": {"winner": "AWAY_TEAM", "fullTime": {"home": 0, "away": 2},
                                  "halfTime": {"home": 0, "away": 2}},
 "referees": [{"id": 11469, "name": "Darren England", "nationality": "England"}],
 "odds": {"msg": "Activate Odds-Package in User-Panel to retrieve odds."}}
```

**What it does not have** — checked `matches/{id}` directly, and there are no
`goals`, `bookings`, `substitutions` or `lineups` keys at any level. Odds are
gated. `scorers` returns goals and assists but `position` comes back `null`.
So: **the spine (fixtures, table, ids, crests, referees), never the detail.**

### API-Football — cannot see this season on the free plan

`x-apisports-key` header, `https://v3.football.api-sports.io/`.
`/status` confirms: plan **Free**, 100 requests/day, 10/min.

The blocker, returned verbatim by `/standings?league=39&season=2026`:

```json
{"results": 0, "errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}}
```

Tested season by season: **2024 works, 2025 and 2026 do not.** `/leagues?id=39`
happily *lists* 2026 with full coverage flags — that is the catalogue, not the
entitlement. So for a 2026/27 project this key is only good for backtesting on
historical seasons unless we upgrade (Pro, $19/mo).

Worth knowing what the upgrade would buy, mapped against a 2023 fixture:

`fixtures/statistics?fixture=` — per team, and it includes xG:

```
Shots on Goal 1 | Shots off Goal 3 | Total Shots 6 | Blocked Shots 2
Shots insidebox 5 | Shots outsidebox 1 | Fouls 11 | Corner Kicks 6 | Offsides 0
Ball Possession 34% | Yellow Cards None | Red Cards 1 | Goalkeeper Saves 5
Total passes 365 | Passes accurate 290 | Passes % 79% | expected_goals 0.33
```

`fixtures/lineups?fixture=` — formation, coach, and **grid coordinates**, which
means lineups can be drawn on a pitch rather than listed:

```json
{"team": {"name": "Burnley"}, "formation": "5-4-1", "coach": {"name": "V. Kompany"},
 "startXI": [{"player": {"id": 162489, "name": "J. Trafford", "number": 1,
                         "pos": "G", "grid": "1:1"}},
             {"player": {"id": 19331,  "name": "C. Roberts",  "number": 14,
                         "pos": "D", "grid": "2:5"}}],
 "substitutes": [...]}
```

Also available on a paid plan: `fixtures/events` (goals, cards, subs with
minutes), `fixtures/players` (per-player match ratings and stats), `injuries`,
`transfers`, `odds`, `predictions`.

---

## Verdict on sourcing

For **2026/27**, the working set is:

- **Understat** — xG, shot locations, PPDA, xPTS. The analysis.
- **FPL API** — player-level xG/xA, minutes, availability, ownership, price.
- **football-data.org** — fixtures, table, referees, crests, stable ids. The spine.
- **API-Football** — parked until/unless we pay; useful now only for backtests
  on 2022-2024.
- **ESPN** — redundant now that football-data.org is authenticated. Drop it.

---

## What the data says right now (live, 3 games played)

```
 #  TEAM                     MP  PTS   xPTS  GF    xG  GA   xGA    xGD  PPDA
 1  Arsenal                   3    9   7.81   6  6.18   1  1.27   4.91   9.5
 2  Manchester City           3    9   6.91   7  7.23   2  3.13   4.10   7.1
 3  Hull                      3    7   2.52   3  2.77   0  4.60  -1.83  19.3
 4  Chelsea                   3    6   4.87   8  6.84   7  6.01   0.83  18.2
...
17  Aston Villa               3    1   2.25   0  2.19   5  6.34  -4.15  20.3
18  Tottenham                 3    1   3.39   0  3.36   5  5.88  -2.52   8.9
20  Coventry                  3    0   3.35   0  3.23   5  4.50  -1.27  16.6
```

Hull sit 3rd on 7 points with **2.52 xPTS** and a *negative* xG difference —
the single loudest regression signal on the board. Tottenham and Coventry have
scored 0 from ~3.3 xG each. Newcastle have 6 goals from 3.38 xG.

That gap between the table and the xG table is the whole project.
