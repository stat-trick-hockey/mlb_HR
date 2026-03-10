# MLB HR Spray Chart

Interactive home run spray chart for all 30 MLB stadiums, powered by the [MLB Stats API](https://statsapi.mlb.com). Live on GitHub Pages with data updated nightly via GitHub Actions.

**[→ View Live Site](https://YOUR-USERNAME.github.io/mlb-hr-spray-chart)**

---

## Features

- All 30 MLB parks with accurate field dimensions
- 2024 full season + 2025 live (updated nightly)
- Filter by stadium, player, or search by name
- Spray chart dots colored by distance, opacity-scaled by exit velocity
- Hover tooltips: distance, exit velo, launch angle, pitcher, date
- Stats panel: avg distance, avg EV, longest HR, distance histogram, top hitters

---

## Setup

### 1. Create the repo and enable GitHub Pages

```bash
git init mlb-hr-spray-chart
cd mlb-hr-spray-chart
# copy all files in, then:
git remote add origin https://github.com/YOUR-USERNAME/mlb-hr-spray-chart.git
```

In your repo settings → **Pages** → Source: **Deploy from a branch** → Branch: `main` / `/ (root)`.

### 2. Bootstrap local data (run once)

The nightly workflow only fetches *new* games. For the initial 2024 full season + 2025-to-date, run the bootstrap script locally:

```bash
pip install requests
python scripts/bootstrap.py
```

This takes ~10–15 minutes (2,500+ games × one API call each). It writes:
- `data/hrs_2024.json`  (~3–5 MB minified)
- `data/hrs_2025.json`

Then commit and push:
```bash
git add data/
git commit -m "chore: initial HR data bootstrap"
git push
```

### 3. Let the nightly workflow run

The workflow at `.github/workflows/update-data.yml` runs at **6 AM UTC daily** (after west coast games finish). It:
1. Fetches the 2025 schedule for any new Final games
2. Extracts home run play-by-play events
3. Appends to `data/hrs_2025.json`
4. Commits back to `main` if there are changes

### 4. Manual trigger

You can also trigger manually from **Actions → Update MLB HR Data → Run workflow**, with options to select season (2024, 2025, or both) and whether to do a full rebuild.

---

## Data structure

`data/hrs_{season}.json`:

```json
{
  "season": 2025,
  "generated_at": "2025-03-09T06:12:34Z",
  "total_home_runs": 1842,
  "games_processed": [746123, 746124, ...],
  "stadiums": { "11": { "name": "Yankee Stadium", "team": "NYY", ... } },
  "home_runs": [
    {
      "gamePk": 746123,
      "date": "2025-04-02",
      "venueId": 11,
      "battingTeam": "New York Yankees",
      "batterName": "Aaron Judge",
      "pitcherName": "Shane Bieber",
      "distance": 449,
      "launchSpeed": 112.4,
      "launchAngle": 26,
      "coordX": 148.2,
      "coordY": 142.7,
      "inning": 4,
      "description": "Aaron Judge homers (3) on a fly ball to left field."
    }
  ]
}
```

---

## Local dev

Just open `index.html` in a browser that serves local files, or use:

```bash
python -m http.server 8000
# → http://localhost:8000
```

The site is fully static — no build step, no dependencies.

---

## Notes

- The MLB Stats API is free and unauthenticated but unofficial. Be respectful of rate limits — the fetch script sleeps 150ms between game calls.
- `coordX`/`coordY` from `hitData.coordinates` may be missing for some older events. The viz falls back to a distance-based estimated position in that case.
- The workflow only updates 2025 data during the regular season. To backfill 2024 changes, use the manual dispatch with `full_rebuild: true`.
