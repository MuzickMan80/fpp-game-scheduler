import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


DEFAULT_FPP_API_URL = "http://192.168.8.2/api/configfile/schedule.json"
DEFAULT_MAPPINGS_FILE = "/home/fpp/media/config/plugin.fpp-game-scheduler.json"
ESPN_SITE_API_BASE = "https://site.api.espn.com"
PLUGIN_MARKER_KEY = "_fppGameScheduler"


def default_mappings() -> List[dict]:
    return [
        {
            "playlist": "brewers",
            "sport": "baseball",
            "league": "mlb",
            "team_name": "Milwaukee Brewers",
            "team_abbr": "MIL",
            "pregame_minutes": 60,
            "game_length_hours": 3.0,
            "postgame_buffer_minutes": 30,
        },
        {
            "playlist": "packers",
            "sport": "football",
            "league": "nfl",
            "team_name": "Green Bay Packers",
            "team_abbr": "GB",
            "pregame_minutes": 60,
            "game_length_hours": 3.5,
            "postgame_buffer_minutes": 30,
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull team schedules and sync matching game windows into FPP."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no POST.")
    parser.add_argument(
        "--days", type=int, default=1, help="Number of days to scan from today."
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
    parser.add_argument(
        "--mappings-file",
        default=DEFAULT_MAPPINGS_FILE,
        help="JSON file containing team-to-playlist mappings.",
    )
    return parser.parse_args()


def parse_utc_datetime(date_value: str) -> datetime:
    if date_value.endswith("Z"):
        date_value = date_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(date_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch.isspace()).strip()


def fetch_json(url: str, headers: Optional[Dict[str, str]] = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=20) as response:
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
        return ("Authorization", f"Basic {base64.b64encode(raw).decode('ascii')}")

    if token:
        return ("Authorization", f"Bearer {token}")
    if username and password:
        raw = f"{username}:{password}".encode("utf-8")
        return ("Authorization", f"Basic {base64.b64encode(raw).decode('ascii')}")
    return None


def fetch_fpp_json(fpp_api_url: str, auth_header: Optional[Tuple[str, str]]) -> dict:
    headers = {"Accept": "application/json"}
    if auth_header:
        headers[auth_header[0]] = auth_header[1]
    return fetch_json(fpp_api_url, headers=headers)


def load_mappings(mappings_file: str) -> List[dict]:
    if not mappings_file:
        return default_mappings()
    if not os.path.exists(mappings_file):
        print(
            f"[WARN] Mappings file '{mappings_file}' not found. Falling back to defaults."
        )
        return default_mappings()

    with open(mappings_file, "r", encoding="utf-8") as file:
        loaded = json.load(file)

    if isinstance(loaded, dict):
        mappings = loaded.get("mappings", [])
    elif isinstance(loaded, list):
        mappings = loaded
    else:
        raise ValueError("Mappings file must contain a list or object with 'mappings'.")

    if not isinstance(mappings, list):
        raise ValueError("Mappings must be a list.")
    return mappings


def league_teams_url(sport: str, league: str) -> str:
    return f"{ESPN_SITE_API_BASE}/apis/site/v2/sports/{sport}/{league}/teams"


def team_schedule_base_url(sport: str, league: str, team_id: str) -> str:
    return f"{ESPN_SITE_API_BASE}/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule"


def build_request_url(base_url: str, dates_value: str) -> str:
    parts = urllib.parse.urlsplit(base_url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["dates"] = dates_value
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )


def resolve_team_id(mapping: dict) -> Optional[str]:
    explicit_id = str(mapping.get("team_id", "")).strip()
    if explicit_id:
        return explicit_id

    sport = str(mapping.get("sport", "")).strip()
    league = str(mapping.get("league", "")).strip()
    if not sport or not league:
        return None

    team_name = normalize(str(mapping.get("team_name", "")))
    team_abbr = normalize(str(mapping.get("team_abbr", "")))
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
        team_id = str(team.get("id", "")).strip()
        if not team_id:
            continue

        display_name = normalize(str(team.get("displayName", "")))
        short_name = normalize(str(team.get("shortDisplayName", "")))
        abbr = normalize(str(team.get("abbreviation", "")))
        slug = normalize(str(team.get("slug", "")))

        score = 0
        if team_abbr and team_abbr == abbr:
            score += 100
        if team_name and team_name == display_name:
            score += 80
        if team_name and team_name == short_name:
            score += 70
        if team_name and team_name in display_name:
            score += 40
        if team_name and team_name in short_name:
            score += 30
        if team_name and team_name in slug:
            score += 20

        if score > best_score:
            best_score = score
            best_match_id = team_id

    return best_match_id if best_score > 0 else None


def collect_games(days: int, mappings: List[dict]) -> List[dict]:
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

    for mapping in mappings:
        playlist = str(mapping.get("playlist", "")).strip()
        sport = str(mapping.get("sport", "")).strip()
        league = str(mapping.get("league", "")).strip()
        team_name = str(mapping.get("team_name", "")).strip()
        team_abbr = str(mapping.get("team_abbr", "")).strip()

        if not playlist or not sport or not league:
            print("[WARN] Skipping mapping missing playlist/sport/league.")
            continue

        pregame_minutes = int(mapping.get("pregame_minutes", 60))
        game_length_hours = float(mapping.get("game_length_hours", 3.0))
        postgame_buffer_minutes = int(mapping.get("postgame_buffer_minutes", 30))

        try:
            team_id = resolve_team_id(mapping)
        except Exception as exc:
            print(f"[WARN] Could not resolve team ID for '{team_name or team_abbr}': {exc}")
            continue

        if not team_id:
            print(f"[WARN] Could not resolve team ID for '{team_name or team_abbr}'.")
            continue

        label_name = team_name or team_abbr or f"{sport}/{league} #{team_id}"
        print(f"[INFO] Mapping '{label_name}' -> ESPN team ID {team_id}, playlist '{playlist}'")

        request_url = build_request_url(team_schedule_base_url(sport, league, team_id), dates_value)
        try:
            data = fetch_json(request_url)
        except urllib.error.URLError as exc:
            print(f"[WARN] Could not fetch schedule for '{label_name}' ({request_url}): {exc}")
            continue
        except json.JSONDecodeError as exc:
            print(f"[WARN] Invalid JSON for '{label_name}' ({request_url}): {exc}")
            continue

        for event in data.get("events", []):
            event_name = event.get("name", "")
            event_date_raw = event.get("date")
            event_id = str(event.get("id", "")).strip()
            if not event_date_raw:
                continue

            try:
                local_kickoff = parse_utc_datetime(event_date_raw)
            except ValueError:
                print(f"[WARN] Unparseable date '{event_date_raw}' in event '{event_name}'")
                continue

            kickoff_day = local_kickoff.date()
            if kickoff_day < start_day or kickoff_day > end_day:
                continue

            unique_key = (playlist, team_id, event_id or event_name, local_kickoff.isoformat())
            if unique_key in seen_event_keys:
                continue
            seen_event_keys.add(unique_key)

            start_show = local_kickoff - timedelta(minutes=pregame_minutes)
            end_show = local_kickoff + timedelta(
                hours=game_length_hours, minutes=postgame_buffer_minutes
            )
            scheduled_slots.append(
                {
                    "playlist": playlist,
                    "startDate": start_show.strftime("%Y-%m-%d"),
                    "endDate": end_show.strftime("%Y-%m-%d"),
                    "startTime": int(start_show.strftime("%H%M%S")),
                    "endTime": int(end_show.strftime("%H%M%S")),
                    "label": event_name,
                    "team_id": team_id,
                    "sport": sport,
                    "league": league,
                }
            )
            print(
                f"[INFO] {label_name}: {event_name} -> "
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
    cleaned_entries = [entry for entry in entries if entry.get(PLUGIN_MARKER_KEY) != 1]

    new_entries = []
    for game in new_games:
        new_entries.append(
            {
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
                PLUGIN_MARKER_KEY: 1,
                "note": game.get("label", ""),
            }
        )

    payload["entries"] = new_entries + cleaned_entries
    return payload


def post_schedule(
    fpp_api_url: str, payload: dict, auth_header: Optional[Tuple[str, str]]
) -> None:
    post_body = payload.get("entries", [])
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth_header:
        headers[auth_header[0]] = auth_header[1]
    request = urllib.request.Request(
        fpp_api_url,
        data=json.dumps(post_body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"FPP returned HTTP {response.status} on update")


def sync_fpp_schedule(
    days: int,
    fpp_api_url: str,
    dry_run: bool,
    auth_header: Optional[Tuple[str, str]],
    mappings: List[dict],
) -> int:
    new_games = collect_games(days=days, mappings=mappings)
    payload = fetch_current_schedule_payload(fpp_api_url, auth_header)
    existing_count = len(payload.get("entries", []))
    merged_payload = merge_entries(payload, new_games)

    print(f"[INFO] Existing entries: {existing_count}")
    print(f"[INFO] New game windows: {len(new_games)}")
    print(f"[INFO] Resulting entries: {len(merged_payload.get('entries', []))}")

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
        mappings = load_mappings(args.mappings_file)
        sync_fpp_schedule(
            days=args.days,
            fpp_api_url=args.fpp_url,
            dry_run=args.dry_run,
            auth_header=auth_header,
            mappings=mappings,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
