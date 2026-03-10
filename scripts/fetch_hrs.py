#!/usr/bin/env python3
"""
fetch_hrs.py — Pulls home run data from the MLB Stats API for a given season.

Data written to:  data/hrs_{season}.json

Strategy:
  - Load existing JSON (if any) to know which gamePks are already processed
  - Fetch schedule for the season, filtered to completed (Final) games
  - For each new gamePk, fetch play-by-play and extract home run events
  - Append new HRs to the existing list and save

Run locally:
  python scripts/fetch_hrs.py --season 2025
  python scripts/fetch_hrs.py --season 2024 --full-rebuild
"""

import argparse
import json
import os
import time
import sys
from datetime import datetime, date
import requests

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
MLB_API   = "https://statsapi.mlb.com/api/v1"
DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
RATE_SLEEP = 0.15   # seconds between game fetches (be polite to the API)
BATCH_SIZE = 20     # games fetched before a brief pause

# Venue ID → stadium metadata (all 30 parks)
STADIUMS = {
    1:   {"name": "Oriole Park at Camden Yards",  "team": "BAL", "lf": 333, "cf": 410, "rf": 318},
    2:   {"name": "Fenway Park",                   "team": "BOS", "lf": 310, "cf": 420, "rf": 302},
    3:   {"name": "Guaranteed Rate Field",         "team": "CWS", "lf": 330, "cf": 400, "rf": 335},
    4:   {"name": "Progressive Field",             "team": "CLE", "lf": 325, "cf": 405, "rf": 325},
    5:   {"name": "Comerica Park",                 "team": "DET", "lf": 345, "cf": 420, "rf": 330},
    7:   {"name": "Kauffman Stadium",              "team": "KCR", "lf": 330, "cf": 410, "rf": 330},
    10:  {"name": "Target Field",                  "team": "MIN", "lf": 339, "cf": 404, "rf": 328},
    11:  {"name": "Yankee Stadium",                "team": "NYY", "lf": 318, "cf": 408, "rf": 314},
    12:  {"name": "Oakland Coliseum",              "team": "OAK", "lf": 330, "cf": 400, "rf": 330},
    13:  {"name": "T-Mobile Park",                 "team": "SEA", "lf": 331, "cf": 401, "rf": 326},
    14:  {"name": "Globe Life Field",              "team": "TEX", "lf": 329, "cf": 407, "rf": 326},
    15:  {"name": "Rogers Centre",                 "team": "TOR", "lf": 328, "cf": 400, "rf": 328},
    16:  {"name": "Wrigley Field",                 "team": "CHC", "lf": 355, "cf": 400, "rf": 353},
    17:  {"name": "Great American Ball Park",      "team": "CIN", "lf": 328, "cf": 404, "rf": 325},
    19:  {"name": "Coors Field",                   "team": "COL", "lf": 347, "cf": 415, "rf": 350},
    22:  {"name": "Dodger Stadium",                "team": "LAD", "lf": 330, "cf": 395, "rf": 330},
    26:  {"name": "American Family Field",         "team": "MIL", "lf": 344, "cf": 400, "rf": 345},
    27:  {"name": "Citi Field",                    "team": "NYM", "lf": 335, "cf": 408, "rf": 330},
    29:  {"name": "Citizens Bank Park",            "team": "PHI", "lf": 329, "cf": 401, "rf": 330},
    31:  {"name": "PNC Park",                      "team": "PIT", "lf": 325, "cf": 399, "rf": 320},
    32:  {"name": "Busch Stadium",                 "team": "STL", "lf": 336, "cf": 400, "rf": 335},
    33:  {"name": "Petco Park",                    "team": "SDP", "lf": 336, "cf": 396, "rf": 322},
    35:  {"name": "Oracle Park",                   "team": "SFG", "lf": 339, "cf": 399, "rf": 309},
    36:  {"name": "Nationals Park",                "team": "WSH", "lf": 336, "cf": 402, "rf": 335},
    2392:{"name": "loanDepot Park",                "team": "MIA", "lf": 344, "cf": 416, "rf": 335},
    2395:{"name": "Minute Maid Park",              "team": "HOU", "lf": 315, "cf": 435, "rf": 326},
    2602:{"name": "Chase Field",                   "team": "ARI", "lf": 330, "cf": 407, "rf": 334},
    2680:{"name": "Tropicana Field",               "team": "TBR", "lf": 315, "cf": 404, "rf": 322},
    2681:{"name": "Angel Stadium",                 "team": "LAA", "lf": 330, "cf": 396, "rf": 330},
    2889:{"name": "Truist Park",                   "team": "ATL", "lf": 335, "cf": 400, "rf": 325},
    4169:{"name": "Sutter Health Park",            "team": "OAK", "lf": 330, "cf": 400, "rf": 330},
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def get(url: str, retries: int = 3) -> dict:
    """GET with simple retry logic."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "mlb-hr-spray-chart/1.0"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  Retry {attempt+1}/{retries} for {url}: {e}")
            time.sleep(2 ** attempt)


def data_path(season: int) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"hrs_{season}.json")


def load_existing(season: int) -> dict:
    path = data_path(season)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        "season": season,
        "generated_at": None,
        "total_home_runs": 0,
        "games_processed": [],
        "stadiums": {},
        "home_runs": []
    }


def save(season: int, data: dict):
    data["generated_at"] = datetime.utcnow().isoformat() + "Z"
    data["total_home_runs"] = len(data["home_runs"])
    path = data_path(season)
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))  # minified
    size_kb = os.path.getsize(path) / 1024
    print(f"  ✓ Saved {path} ({len(data['home_runs'])} HRs, {size_kb:.1f} KB)")


# ─────────────────────────────────────────────
# Schedule
# ─────────────────────────────────────────────

# Human-readable labels for gameType codes
GAME_TYPE_LABELS = {
    "R": "Regular Season",
    "F": "Wild Card",
    "D": "Division Series",
    "L": "League Championship",
    "W": "World Series",
}

PLAYOFF_GAME_TYPES = ["F", "D", "L", "W"]
ALL_GAME_TYPES     = ["R"] + PLAYOFF_GAME_TYPES


def fetch_schedule(season: int) -> list[dict]:
    """Return list of game metadata dicts for all Final regular season + playoff games."""
    print(f"Fetching {season} schedule (regular season + playoffs)…")

    # Season date ranges
    if season == 2024:
        start, end = "2024-03-20", "2024-11-05"
    elif season == 2025:
        start, end = "2025-03-18", "2025-11-05"
    else:
        # 2026: up to today
        start = "2026-03-25"
        end = date.today().isoformat()

    # Fetch all game types in one call
    game_types_param = "&".join(f"gameType={t}" for t in ALL_GAME_TYPES)
    url = (f"{MLB_API}/schedule?sportId=1"
           f"&startDate={start}&endDate={end}"
           f"&{game_types_param}"
           f"&hydrate=venue,teams")
    data = get(url)

    games = []
    venues = {}   # venueId -> {name, team} collected from live API data

    for day in data.get("dates", []):
        for g in day.get("games", []):
            if g.get("status", {}).get("abstractGameCode") != "F":
                continue  # skip non-final
            raw_type = g.get("gameType", "R")

            # Collect venue metadata from API response
            venue = g.get("venue", {})
            vid = venue.get("id")
            if vid and vid not in venues:
                home_team = g.get("teams", {}).get("home", {}).get("team", {})
                venues[vid] = {
                    "name": venue.get("name", f"Venue {vid}"),
                    "team": home_team.get("abbreviation", ""),
                    "teamName": home_team.get("name", ""),
                    # Dimensions not in schedule API — use fallback if available
                    "lf":  STADIUMS.get(vid, {}).get("lf"),
                    "cf":  STADIUMS.get(vid, {}).get("cf"),
                    "rf":  STADIUMS.get(vid, {}).get("rf"),
                }

            games.append({
                "gamePk":        g["gamePk"],
                "date":          day["date"],
                "gameType":      raw_type,
                "gameTypeLabel": GAME_TYPE_LABELS.get(raw_type, raw_type),
                "venueId":       vid,
                "homeTeamId":    g.get("teams", {}).get("home", {}).get("team", {}).get("id"),
                "awayTeamId":    g.get("teams", {}).get("away", {}).get("team", {}).get("id"),
                "homeName":      g.get("teams", {}).get("home", {}).get("team", {}).get("name", ""),
                "awayName":      g.get("teams", {}).get("away", {}).get("team", {}).get("name", ""),
            })

    reg     = sum(1 for g in games if g["gameType"] == "R")
    playoff = sum(1 for g in games if g["gameType"] != "R")
    print(f"  Found {reg} regular season + {playoff} playoff games ({len(games)} total)")
    print(f"  Discovered {len(venues)} unique venues")
    return games, venues


# ─────────────────────────────────────────────
# Play-by-play extraction
# ─────────────────────────────────────────────
def extract_hrs_from_game(game_meta: dict) -> list[dict]:
    """Fetch play-by-play for one game and return all home run events."""
    gk = game_meta["gamePk"]
    try:
        data = get(f"{MLB_API}/game/{gk}/playByPlay")
    except Exception as e:
        print(f"    ✗ gamePk {gk}: {e}")
        return []

    hrs = []
    for play in data.get("allPlays", []):
        if play.get("result", {}).get("eventType") != "home_run":
            continue

        batter  = play.get("matchup", {}).get("batter", {})
        pitcher = play.get("matchup", {}).get("pitcher", {})
        about   = play.get("about", {})

        # hitData lives on the last play event
        events   = play.get("playEvents", [])
        hit_data = events[-1].get("hitData", {}) if events else {}
        coords   = hit_data.get("coordinates", {})

        # Determine batting team
        half = about.get("halfInning", "")
        batting_team_id = game_meta["homeTeamId"] if half == "bottom" else game_meta["awayTeamId"]
        batting_team    = game_meta["homeName"]   if half == "bottom" else game_meta["awayName"]

        hrs.append({
            "gamePk":        gk,
            "date":          game_meta["date"],
            "gameType":      game_meta["gameType"],
            "gameTypeLabel": game_meta["gameTypeLabel"],
            "venueId":       game_meta["venueId"],
            "battingTeamId": batting_team_id,
            "battingTeam":   batting_team,
            "batterId":      batter.get("id"),
            "batterName":    batter.get("fullName", "Unknown"),
            "pitcherId":     pitcher.get("id"),
            "pitcherName":   pitcher.get("fullName", "Unknown"),
            "inning":        about.get("inning"),
            "halfInning":    half,
            "distance":      hit_data.get("totalDistance"),
            "launchSpeed":   hit_data.get("launchSpeed"),
            "launchAngle":   hit_data.get("launchAngle"),
            "hardness":      hit_data.get("hardness"),
            "coordX":        coords.get("coordX"),
            "coordY":        coords.get("coordY"),
            "description":   play.get("result", {}).get("description", ""),
        })

    return hrs


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def run(season: int, full_rebuild: bool = False):
    print(f"\n{'='*50}")
    print(f" MLB HR Fetch — Season {season}")
    print(f"{'='*50}")

    existing = load_existing(season)

    if full_rebuild:
        print("  Full rebuild requested — clearing existing data")
        existing["home_runs"] = []
        existing["games_processed"] = []

    processed_set = set(existing["games_processed"])
    games, venues = fetch_schedule(season)

    # Merge newly discovered venues (API names always win)
    existing["stadiums"].update({str(k): v for k, v in venues.items()})

    new_games = [g for g in games if g["gamePk"] not in processed_set]
    print(f"  {len(processed_set)} games already processed, {len(new_games)} new to fetch")

    if not new_games:
        print("  Nothing new. Done.")
        return

    new_hrs = []
    for i, game in enumerate(new_games, 1):
        hrs = extract_hrs_from_game(game)
        new_hrs.extend(hrs)
        existing["games_processed"].append(game["gamePk"])

        if i % 10 == 0 or i == len(new_games):
            print(f"  [{i}/{len(new_games)}] +{len(hrs)} HRs → {len(existing['home_runs']) + len(new_hrs)} total")

        time.sleep(RATE_SLEEP)
        if i % BATCH_SIZE == 0:
            time.sleep(1)  # longer pause between batches

    existing["home_runs"].extend(new_hrs)
    save(season, existing)
    print(f"\n  Done. Added {len(new_hrs)} new HRs from {len(new_games)} games.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch MLB HR data")
    parser.add_argument("--season", type=int, choices=[2024, 2025, 2026], required=True)
    parser.add_argument("--full-rebuild", action="store_true",
                        help="Wipe existing data and re-fetch everything")
    args = parser.parse_args()
    run(args.season, args.full_rebuild)
