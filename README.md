# FPP Game Scheduler Plugin (Starter)

This repository includes a Falcon Player (FPP) plugin scaffold that wraps
`fpp_game_scheduler_sync.py` and exposes an in-FPP configuration page.

The plugin is mapping-driven: you can connect any FPP playlist to any ESPN team
by sport/league/team in the UI.

## Included Plugin Files

- `pluginInfo.json` - plugin metadata for FPP Plugin Manager
- `output_menu.inc` - menu entry under Output Setup
- `fpp_game_scheduler.php` - plugin configuration page with team-to-playlist mappings
- `scripts/run_sync.sh` - helper script for command-line/cron execution
- `fpp_game_scheduler_sync.py` - ESPN -> FPP schedule sync engine

## Install (manual)

1. Copy or clone this repo to:
   - `/home/fpp/media/plugins/fpp-game-scheduler`
2. Ensure Python 3 is installed on FPP.
3. Ensure run script is executable:
   - `chmod +x /home/fpp/media/plugins/fpp-game-scheduler/scripts/run_sync.sh`
4. Open FPP UI and navigate to:
   - `Output Setup` -> `Game Scheduler`

## Configuration Data

Plugin settings are stored in:

- `/home/fpp/media/config/plugin.fpp-game-scheduler.json`

Each mapping row stores:

- `sport` and `league` slugs (for ESPN API path)
- selected `team_id` / `team_name` / `team_abbr`
- target `playlist`
- timing offsets (`pregame_minutes`, `game_length_hours`, `postgame_buffer_minutes`)

## License

MIT (see `LICENSE`).

## Run From Shell

- Dry run:
  - `DRY_RUN=1 /home/fpp/media/plugins/fpp-game-scheduler/scripts/run_sync.sh`
- Live update:
  - `/home/fpp/media/plugins/fpp-game-scheduler/scripts/run_sync.sh`

## Notes

- Update `pluginInfo.json` URLs (`homeURL`, `srcURL`, `bugURL`) to your real repo.
- ESPN endpoints are unofficial and may change, so keep fallback plans in mind.
