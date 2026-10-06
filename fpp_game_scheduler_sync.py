import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


# Default FPP schedule config endpoint.
# Adjust this if your FPP instance is on another host or path.
DEFAULT_FPP_API_URL = "http://192.168.8.2/api/configfile/schedule.json"
ESPN_SITE_API_BASE = "https://site.api.espn.com"


TEAMS: Dict[str, Dict[str, object]] = {
    "brewers": {
        "sport": "baseball",
        "league": "mlb",
        "team_query": "Milwaukee Brewers",
        "abbreviation": "MIL",
        "name": "Brewers",
        "game_length_hours": 3.0,
    },
    "packers": {
        "sport": "football",
        "league": "nfl",
        "team_query": "Green Bay Packers",
        "abbreviation": "GB",
        "name": "Packers",
        "game_length_hours": 3.5,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull team schedules and sync matching game windows into FPP."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print changes but do not POST updates to FPP.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to scan starting today (default: 1).",
    )
    parser.add_argument(
        "--fpp-url",
        default=DEFAULT_FPP_API_URL,
        help=f"FPP schedule API URL (default: {DEFAULT_FPP_API_URL}).",
    )
    parser.add_argument(
        "--fpp-auth",
        choices=["auto", "none", "basic", "bearer"],
        default="auto",
        help="FPP auth mode: auto (default), none, basic, or bearer token.",
    )
    parser.add_argument(
        "--fpp-username",
        default=os.getenv("FPP_USERNAME", ""),
        help="FPP username for basic auth (or set FPP_USERNAME).",
    )
    parser.add_argument(
        "--fpp-password",
        default=os.getenv("FPP_PASSWORD", ""),
        help="FPP password for basic auth (or set FPP_PASSWORD).",
    )
    parser.add_argument(
        "--fpp-token",
        default=os.getenv("FPP_TOKEN", ""),
        help="FPP bearer token (or set FPP_TOKEN).",
    )
    return parser.parse_args()


def parse_utc_datetime(date_value: str) -> datetime:
    # ESPN commonly returns UTC strings ending in Z.
    if date_value.endswith("Z"):
        date_value = date_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(date_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def build_fpp_auth_header(
    auth_mode: str, username: str, password: str, token: str
) -> Optional[Tuple[str, str]]:
    auth_mode = auth_mode.lower().strip()
    username = username.strip()
    token = token.strip()

    if auth_mode == "none":
        return None
    if auth_mode == "bearer":
        if not token:
            raise ValueError("--fpp-auth bearer requires --fpp-token (or FPP_TOKEN)")
        return ("Authorization", f"Bearer {token}")
    if auth_mode == "basic":
        if not username or not password:
            raise ValueError(
                "--fpp-auth basic requires --fpp-username and --fpp-password "
                "(or FPP_USERNAME/FPP_PASSWORD)"
            )
        raw = f"{username}:{password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return ("Authorization", f"Basic {encoded}")

    # auto
    if token:
        return ("Authorization", f"Bearer {token}")
    if username and password:
        raw = f"{username}:{password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return ("Authorization", f"Basic {encoded}")
    return None


def fetch_fpp_json(fpp_api_url: str, auth_header: Optional[Tuple[str, str]]) -> dict:
    headers = {"Accept": "application/json"}
    if auth_header:
        headers[auth_header[0]] = auth_header[1]
    req = urllib.request.Request(fpp_api_url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch.isspace()).strip()


def league_teams_url(sport: str, league: str) -> str:
    return f"{ESPN_SITE_API_BASE}/apis/site/v2/sports/{sport}/{league}/teams"


def team_schedule_base_url(sport: str, league: str, team_id: str) -> str:
    return f"{ESPN_SITE_API_BASE}/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule"


def resolve_team_id(team_info: Dict[str, object]) -> Optional[str]:
    sport = str(team_info["sport"])
    league = str(team_info["league"])
    team_query = normalize(str(team_info.get("team_query", "")))
    abbreviation = normalize(str(team_info.get("abbreviation", "")))

    data = fetch_json(league_teams_url(sport, league))
    sports = data.get("sports", [])
    if not sports:
        return None

    leagues = sports[0].get("leagues", [])
    if not leagues:
        return None

    best_match_id = None
    best_score = -1

    for wrapped in leagues[0].get("teams", []):
        team = wrapped.get("team", {})
        if not isinstance(team, dict):
            continue

        display_name = normalize(str(team.get("displayName", "")))
        short_name = normalize(str(team.get("shortDisplayName", "")))
        name = normalize(str(team.get("name", "")))
        abbr = normalize(str(team.get("abbreviation", "")))
        slug = normalize(str(team.get("slug", "")))
        team_id = str(team.get("id", "")).strip()
        if not team_id:
            continue

        score = 0
        if abbreviation and abbreviation == abbr:
            score += 100
        if team_query and team_query == display_name:
            score += 80
        if team_query and team_query == short_name:
            score += 70
        if team_query and team_query == name:
            score += 60
        if team_query and team_query in display_name:
            score += 40
        if team_query and team_query in short_name:
            score += 30
        if team_query and team_query in slug:
            score += 20

        if score > best_score:
            best_score = score
            best_match_id = team_id

    return best_match_id if best_score > 0 else None


def build_request_url(base_url: str, day_yyyymmdd: str) -> str:
    parts = urllib.parse.urlsplit(base_url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["dates"] = day_yyyymmdd
    new_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )


def collect_games(days: int) -> List[dict]:
    if days < 1:
        raise ValueError("--days must be at least 1")

    now_local = datetime.now().astimezone()
    start_day = now_local.date()
    end_day = start_day + timedelta(days=days - 1)
    start_yyyymmdd = start_day.strftime("%Y%m%d")
    end_yyyymmdd = end_day.strftime("%Y%m%d")
    dates_value = start_yyyymmdd if days == 1 else f"{start_yyyymmdd}-{end_yyyymmdd}"

    scheduled_slots: List[dict] = []
    seen_event_keys = set()

    resolved_team_ids: Dict[str, str] = {}

    for playlist_name, info in TEAMS.items():
        team_name = str(info["name"])
        sport = str(info["sport"])
        league = str(info["league"])
        game_length_hours = float(info.get("game_length_hours", 3.0))

        team_id = resolved_team_ids.get(playlist_name)
        if not team_id:
            try:
                team_id = resolve_team_id(info)
            except Exception as exc:
                print(f"[WARN] Could not resolve ESPN team ID for {team_name}: {exc}")
                continue
            if not team_id:
                print(f"[WARN] Could not resolve ESPN team ID for {team_name}")
                continue
            resolved_team_ids[playlist_name] = team_id
            print(f"[INFO] Resolved {team_name} to ESPN team ID {team_id}")

        base_url = team_schedule_base_url(sport, league, team_id)
        request_url = build_request_url(base_url, dates_value)

        try:
            data = fetch_json(request_url)
        except urllib.error.URLError as exc:
            print(f"[WARN] Could not fetch {team_name} schedule ({request_url}): {exc}")
            continue
        except json.JSONDecodeError as exc:
            print(f"[WARN] Invalid JSON for {team_name} ({request_url}): {exc}")
            continue

        for event in data.get("events", []):
            event_name = event.get("name", "")
            event_date_raw = event.get("date")
            event_id = str(event.get("id", ""))
            if not event_date_raw:
                continue

            try:
                local_kickoff = parse_utc_datetime(event_date_raw)
            except ValueError:
                print(f"[WARN] Unparseable date '{event_date_raw}' in event '{event_name}'")
                continue

            # Some ESPN team schedule endpoints still return full season;
            # keep only events in the requested local date window.
            kickoff_day = local_kickoff.date()
            if kickoff_day < start_day or kickoff_day > end_day:
                continue

            unique_key = (playlist_name, event_id or event_name, local_kickoff.isoformat())
            if unique_key in seen_event_keys:
                continue
            seen_event_keys.add(unique_key)

            start_show = local_kickoff - timedelta(hours=1)
            end_show = local_kickoff + timedelta(hours=game_length_hours, minutes=30)

            slot = {
                "playlist": playlist_name,
                "startDate": start_show.strftime("%Y-%m-%d"),
                "endDate": end_show.strftime("%Y-%m-%d"),
                "startTime": int(start_show.strftime("%H%M%S")),
                "endTime": int(end_show.strftime("%H%M%S")),
                "label": event_name,
            }
            scheduled_slots.append(slot)
            print(
                f"[INFO] {team_name}: {event_name} -> "
                f"{start_show.strftime('%Y-%m-%d %H:%M')} to {end_show.strftime('%Y-%m-%d %H:%M')}"
            )

    return scheduled_slots


def fetch_current_schedule_payload(
    fpp_api_url: str, auth_header: Optional[Tuple[str, str]]
) -> dict:
    try:
        payload = fetch_fpp_json(fpp_api_url, auth_header)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(
                f"FPP auth failed with HTTP {exc.code}. "
                "Provide credentials using --fpp-auth/--fpp-username/--fpp-password "
                "or --fpp-token."
            ) from exc
        raise RuntimeError(f"Failed to fetch current schedule from FPP: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch current schedule from FPP: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"FPP returned invalid JSON for schedule: {exc}") from exc

    # FPP may return either:
    # 1) a raw array of schedule entries, or
    # 2) an object wrapper containing "entries".
    if isinstance(payload, list):
        payload = {"entries": payload}
    elif not isinstance(payload, dict):
        raise RuntimeError("Unexpected FPP payload format: expected object or array")

    entries = payload.get("entries")
    if entries is None:
        payload["entries"] = []
    elif not isinstance(entries, list):
        raise RuntimeError("Unexpected FPP payload format: 'entries' is not a list")

    return payload


def merge_entries(payload: dict, new_games: List[dict]) -> dict:
    entries = payload.get("entries", [])
    managed_playlists = set(TEAMS.keys())

    cleaned_entries = [
        entry for entry in entries if entry.get("playlist") not in managed_playlists
    ]

    new_entries = []
    for game in new_games:
        new_entry = {
            "enabled": 1,
            "playlist": game["playlist"],
            "type": "playlist",
            "startDay": 0,
            "endDay": 6,
            "startTime": game["startTime"],
            "endTime": game["endTime"],
            "startDate": game["startDate"],
            "endDate": game["endDate"],
            "repeat": 1,
        }
        new_entries.append(new_entry)

    payload["entries"] = new_entries + cleaned_entries
    return payload


def post_schedule(
    fpp_api_url: str, payload: dict, auth_header: Optional[Tuple[str, str]]
) -> None:
    # Send back a raw schedule array for compatibility with configfile semantics.
    post_body = payload.get("entries", [])
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth_header:
        headers[auth_header[0]] = auth_header[1]
    req = urllib.request.Request(
        fpp_api_url,
        data=json.dumps(post_body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"FPP returned HTTP {response.status} on update")


def sync_fpp_schedule(
    days: int, fpp_api_url: str, dry_run: bool, auth_header: Optional[Tuple[str, str]]
) -> int:
    new_games = collect_games(days=days)
    payload = fetch_current_schedule_payload(fpp_api_url, auth_header)
    existing_count = len(payload.get("entries", []))
    merged_payload = merge_entries(payload, new_games)
    merged_count = len(merged_payload.get("entries", []))

    print(f"[INFO] Existing entries: {existing_count}")
    print(f"[INFO] New game windows: {len(new_games)}")
    print(f"[INFO] Resulting entries: {merged_count}")

    if dry_run:
        print("[DRY-RUN] No changes posted to FPP.")
        print(json.dumps(merged_payload, indent=2))
        return len(new_games)

    post_schedule(fpp_api_url, merged_payload, auth_header)
    print(f"[INFO] Schedule updated successfully. Added/updated {len(new_games)} game windows.")
    return len(new_games)


def main() -> int:
    args = parse_args()
    try:
        auth_header = build_fpp_auth_header(
            auth_mode=args.fpp_auth,
            username=args.fpp_username,
            password=args.fpp_password,
            token=args.fpp_token,
        )
        sync_fpp_schedule(
            days=args.days,
            fpp_api_url=args.fpp_url,
            dry_run=args.dry_run,
            auth_header=auth_header,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
