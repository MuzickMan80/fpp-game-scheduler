<?php
/*
 * FPP plugin page rendered via:
 *   plugin.php?plugin=fpp-game-scheduler&page=fpp_game_scheduler.php
 */

function h($value)
{
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function respond_json($data, $status = 200)
{
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_UNESCAPED_SLASHES);
    exit;
}

function fetch_json_url($url)
{
    $context = stream_context_create(array(
        'http' => array(
            'method' => 'GET',
            'timeout' => 20
        )
    ));
    $raw = @file_get_contents($url, false, $context);
    if ($raw === false) {
        return null;
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : null;
}

function load_settings($path, $defaults)
{
    if (!file_exists($path)) {
        return $defaults;
    }
    $raw = file_get_contents($path);
    if ($raw === false) {
        return $defaults;
    }
    $decoded = json_decode($raw, true);
    if (!is_array($decoded)) {
        return $defaults;
    }
    return array_merge($defaults, $decoded);
}

function save_settings($path, $settings)
{
    $dir = dirname($path);
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    return file_put_contents(
        $path,
        json_encode($settings, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL
    ) !== false;
}

function normalize_mappings($value)
{
    $rows = is_array($value) ? $value : array();
    $clean = array();
    foreach ($rows as $row) {
        if (!is_array($row)) {
            continue;
        }
        $playlist = trim((string)($row['playlist'] ?? ''));
        $sport = trim((string)($row['sport'] ?? ''));
        $league = trim((string)($row['league'] ?? ''));
        if ($playlist === '' || $sport === '' || $league === '') {
            continue;
        }
        $clean[] = array(
            'playlist' => $playlist,
            'sport' => $sport,
            'league' => $league,
            'team_id' => trim((string)($row['team_id'] ?? '')),
            'team_name' => trim((string)($row['team_name'] ?? '')),
            'team_abbr' => trim((string)($row['team_abbr'] ?? '')),
            'pregame_minutes' => max(0, (int)($row['pregame_minutes'] ?? 60)),
            'game_length_hours' => max(0.5, (float)($row['game_length_hours'] ?? 3.0)),
            'postgame_buffer_minutes' => max(0, (int)($row['postgame_buffer_minutes'] ?? 30))
        );
    }
    return $clean;
}

function extract_playlists($payload)
{
    $items = array();
    if (is_array($payload)) {
        if (isset($payload['playlists']) && is_array($payload['playlists'])) {
            $items = $payload['playlists'];
        } else {
            $items = $payload;
        }
    }

    $names = array();
    foreach ($items as $item) {
        if (is_string($item)) {
            $name = trim($item);
        } elseif (is_array($item)) {
            $name = trim((string)($item['name'] ?? $item['playlistName'] ?? $item['playlist'] ?? ''));
        } else {
            $name = '';
        }
        if ($name !== '') {
            $names[$name] = true;
        }
    }
    $result = array_keys($names);
    sort($result, SORT_NATURAL | SORT_FLAG_CASE);
    return $result;
}

function get_fpp_playlists()
{
    $payload = fetch_json_url('http://127.0.0.1/api/playlists');
    if (!is_array($payload)) {
        return array();
    }
    return extract_playlists($payload);
}

function get_espn_teams($sport, $league)
{
    $sport = trim((string)$sport);
    $league = trim((string)$league);
    if ($sport === '' || $league === '') {
        return array();
    }

    $url = 'https://site.api.espn.com/apis/site/v2/sports/' . rawurlencode($sport) . '/' . rawurlencode($league) . '/teams';
    $payload = fetch_json_url($url);
    if (!is_array($payload)) {
        return array();
    }

    $teams = array();
    $sports = $payload['sports'] ?? array();
    $leagues = (isset($sports[0]['leagues']) && is_array($sports[0]['leagues'])) ? $sports[0]['leagues'] : array();
    $wrappedTeams = (isset($leagues[0]['teams']) && is_array($leagues[0]['teams'])) ? $leagues[0]['teams'] : array();
    foreach ($wrappedTeams as $wrapped) {
        $team = is_array($wrapped) ? ($wrapped['team'] ?? array()) : array();
        if (!is_array($team)) {
            continue;
        }
        $id = trim((string)($team['id'] ?? ''));
        $name = trim((string)($team['displayName'] ?? $team['shortDisplayName'] ?? ''));
        if ($id === '' || $name === '') {
            continue;
        }
        $teams[] = array(
            'id' => $id,
            'name' => $name,
            'abbr' => trim((string)($team['abbreviation'] ?? ''))
        );
    }

    usort($teams, function ($a, $b) {
        return strcasecmp($a['name'], $b['name']);
    });
    return $teams;
}

$pluginName = isset($_GET['plugin']) ? basename((string)$_GET['plugin']) : 'fpp-game-scheduler';
$pluginDir = '/home/fpp/media/plugins/' . $pluginName;
$settingsPath = '/home/fpp/media/config/plugin.' . $pluginName . '.json';
$scriptPath = $pluginDir . '/fpp_game_scheduler_sync.py';
$selfUrl = 'plugin.php?plugin=' . rawurlencode($pluginName) . '&page=fpp_game_scheduler.php';

if ($_SERVER['REQUEST_METHOD'] === 'GET' && isset($_GET['api'])) {
    $api = (string)$_GET['api'];
    if ($api === 'teams') {
        $sport = (string)($_GET['sport'] ?? '');
        $league = (string)($_GET['league'] ?? '');
        respond_json(array('teams' => get_espn_teams($sport, $league)));
    } elseif ($api === 'playlists') {
        respond_json(array('playlists' => get_fpp_playlists()));
    }
    respond_json(array('error' => 'Unknown API endpoint.'), 404);
}

$defaults = array(
    'fpp_url' => 'http://127.0.0.1/api/configfile/schedule.json',
    'days' => 3,
    'fpp_auth' => 'auto',
    'fpp_username' => '',
    'fpp_password' => '',
    'fpp_token' => '',
    'mappings' => array(
        array(
            'playlist' => 'brewers',
            'sport' => 'baseball',
            'league' => 'mlb',
            'team_id' => '',
            'team_name' => 'Milwaukee Brewers',
            'team_abbr' => 'MIL',
            'pregame_minutes' => 60,
            'game_length_hours' => 3.0,
            'postgame_buffer_minutes' => 30
        ),
        array(
            'playlist' => 'packers',
            'sport' => 'football',
            'league' => 'nfl',
            'team_id' => '',
            'team_name' => 'Green Bay Packers',
            'team_abbr' => 'GB',
            'pregame_minutes' => 60,
            'game_length_hours' => 3.5,
            'postgame_buffer_minutes' => 30
        )
    )
);

$settings = load_settings($settingsPath, $defaults);
if (!isset($settings['mappings']) || !is_array($settings['mappings'])) {
    $settings['mappings'] = $defaults['mappings'];
}

$messages = array();
$commandOutput = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = isset($_POST['action']) ? (string)$_POST['action'] : '';

    if ($action === 'save') {
        $settings['fpp_url'] = trim((string)($_POST['fpp_url'] ?? $settings['fpp_url']));
        $settings['days'] = max(1, (int)($_POST['days'] ?? $settings['days']));
        $auth = strtolower(trim((string)($_POST['fpp_auth'] ?? $settings['fpp_auth'])));
        $settings['fpp_auth'] = in_array($auth, array('auto', 'none', 'basic', 'bearer'), true) ? $auth : 'auto';
        $settings['fpp_username'] = trim((string)($_POST['fpp_username'] ?? ''));
        $settings['fpp_password'] = (string)($_POST['fpp_password'] ?? '');
        $settings['fpp_token'] = trim((string)($_POST['fpp_token'] ?? ''));

        $mappingsJson = (string)($_POST['mappings_json'] ?? '[]');
        $decodedMappings = json_decode($mappingsJson, true);
        $settings['mappings'] = normalize_mappings($decodedMappings);

        if (count($settings['mappings']) === 0) {
            $messages[] = 'No valid mappings were saved. Add at least one row with playlist/sport/league.';
        } elseif (save_settings($settingsPath, $settings)) {
            $messages[] = 'Settings saved.';
        } else {
            $messages[] = 'Failed to save settings.';
        }
    } elseif ($action === 'run') {
        $runDry = isset($_POST['run_dry']);
        $runDays = max(1, (int)($_POST['run_days'] ?? $settings['days']));

        if (!file_exists($scriptPath)) {
            $messages[] = 'Sync script not found at ' . $scriptPath;
        } elseif (!file_exists($settingsPath)) {
            $messages[] = 'Save settings first so mappings can be loaded.';
        } else {
            putenv('FPP_USERNAME=' . (string)$settings['fpp_username']);
            putenv('FPP_PASSWORD=' . (string)$settings['fpp_password']);
            putenv('FPP_TOKEN=' . (string)$settings['fpp_token']);

            $pythonBin = trim((string)shell_exec('command -v python3'));
            if ($pythonBin === '') {
                $pythonBin = 'python3';
            }

            $parts = array(
                escapeshellarg($pythonBin),
                escapeshellarg($scriptPath),
                '--fpp-url', escapeshellarg((string)$settings['fpp_url']),
                '--fpp-auth', escapeshellarg((string)$settings['fpp_auth']),
                '--days', escapeshellarg((string)$runDays),
                '--mappings-file', escapeshellarg($settingsPath)
            );
            if ($runDry) {
                $parts[] = '--dry-run';
            }

            $cmd = implode(' ', $parts) . ' 2>&1';
            $outputLines = array();
            $exitCode = 0;
            exec($cmd, $outputLines, $exitCode);
            $commandOutput = implode(PHP_EOL, $outputLines);
            $messages[] = 'Run complete with exit code ' . $exitCode . '.';
        }
    }
}

$playlistOptions = get_fpp_playlists();
?>

<div class="container-fluid">
    <h2>FPP Game Scheduler</h2>
    <p>Map any ESPN team to any FPP playlist and sync game windows automatically.</p>

    <?php foreach ($messages as $msg): ?>
        <div class="alert alert-info" role="alert"><?php echo h($msg); ?></div>
    <?php endforeach; ?>

    <div class="row">
        <div class="col-md-8">
            <div class="fpp-card">
                <div class="fpp-card-title">Settings & Team Mappings</div>
                <div class="fpp-card-body">
                    <form method="post" id="settingsForm">
                        <input type="hidden" name="action" value="save">
                        <input type="hidden" name="mappings_json" id="mappings_json" value="">

                        <div class="mb-3">
                            <label for="fpp_url" class="form-label">FPP Schedule API URL</label>
                            <input id="fpp_url" name="fpp_url" class="form-control" type="text" value="<?php echo h($settings['fpp_url']); ?>">
                        </div>

                        <div class="mb-3">
                            <label for="days" class="form-label">Default Days Lookahead</label>
                            <input id="days" name="days" class="form-control" type="number" min="1" max="30" value="<?php echo h($settings['days']); ?>">
                        </div>

                        <div class="mb-3">
                            <label for="fpp_auth" class="form-label">FPP Auth Mode</label>
                            <select id="fpp_auth" name="fpp_auth" class="form-control">
                                <?php
                                $authModes = array('auto' => 'auto', 'none' => 'none', 'basic' => 'basic', 'bearer' => 'bearer');
                                foreach ($authModes as $value => $label) {
                                    $selected = ($settings['fpp_auth'] === $value) ? 'selected' : '';
                                    echo '<option value="' . h($value) . '" ' . $selected . '>' . h($label) . '</option>';
                                }
                                ?>
                            </select>
                        </div>

                        <div class="mb-3">
                            <label for="fpp_username" class="form-label">FPP Username (basic auth)</label>
                            <input id="fpp_username" name="fpp_username" class="form-control" type="text" value="<?php echo h($settings['fpp_username']); ?>">
                        </div>

                        <div class="mb-3">
                            <label for="fpp_password" class="form-label">FPP Password (basic auth)</label>
                            <input id="fpp_password" name="fpp_password" class="form-control" type="password" value="<?php echo h($settings['fpp_password']); ?>">
                        </div>

                        <div class="mb-3">
                            <label for="fpp_token" class="form-label">FPP Bearer Token</label>
                            <input id="fpp_token" name="fpp_token" class="form-control" type="password" value="<?php echo h($settings['fpp_token']); ?>">
                        </div>

                        <hr>
                        <h4>Team → Playlist Mappings</h4>
                        <p class="text-muted">Use ESPN sport/league slugs (examples: football/nfl, baseball/mlb, basketball/nba).</p>
                        <table class="table table-sm" id="mappingsTable">
                            <thead>
                                <tr>
                                    <th>Sport</th>
                                    <th>League</th>
                                    <th>Team</th>
                                    <th>Playlist</th>
                                    <th>Pregame (m)</th>
                                    <th>Game (h)</th>
                                    <th>Post (m)</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody id="mappingsBody"></tbody>
                        </table>
                        <button type="button" class="btn btn-secondary btn-sm" id="addMappingBtn">Add Mapping</button>
                        <button class="btn btn-primary" type="submit">Save Settings</button>
                    </form>
                </div>
            </div>
        </div>

        <div class="col-md-4">
            <div class="fpp-card">
                <div class="fpp-card-title">Run Sync</div>
                <div class="fpp-card-body">
                    <form method="post">
                        <input type="hidden" name="action" value="run">
                        <div class="mb-3">
                            <label for="run_days" class="form-label">Days to Scan</label>
                            <input id="run_days" name="run_days" class="form-control" type="number" min="1" max="30" value="<?php echo h($settings['days']); ?>">
                        </div>
                        <div class="form-check mb-3">
                            <input id="run_dry" name="run_dry" class="form-check-input" type="checkbox" checked>
                            <label class="form-check-label" for="run_dry">Dry Run (preview only)</label>
                        </div>
                        <button class="btn btn-success" type="submit">Run Now</button>
                        <p class="small text-muted mt-2">Run uses last saved mappings.</p>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <?php if ($commandOutput !== ''): ?>
        <div class="row mt-3">
            <div class="col-md-12">
                <div class="fpp-card">
                    <div class="fpp-card-title">Last Run Output</div>
                    <div class="fpp-card-body">
                        <pre style="white-space: pre-wrap;"><?php echo h($commandOutput); ?></pre>
                    </div>
                </div>
            </div>
        </div>
    <?php endif; ?>
</div>

<script>
(function () {
    const apiBase = <?php echo json_encode($selfUrl, JSON_UNESCAPED_SLASHES); ?>;
    const initialMappings = <?php echo json_encode($settings['mappings'], JSON_UNESCAPED_SLASHES); ?>;
    const playlists = <?php echo json_encode($playlistOptions, JSON_UNESCAPED_SLASHES); ?>;

    const body = document.getElementById('mappingsBody');
    const addBtn = document.getElementById('addMappingBtn');
    const form = document.getElementById('settingsForm');
    const mappingsInput = document.getElementById('mappings_json');

    function makePlaylistSelect(selected) {
        const select = document.createElement('select');
        select.className = 'form-control form-control-sm playlist';
        playlists.forEach((name) => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            if (name === selected) option.selected = true;
            select.appendChild(option);
        });
        return select;
    }

    async function loadTeamsForRow(row, preferTeamId, preferTeamName, preferTeamAbbr) {
        const sport = row.querySelector('.sport').value.trim();
        const league = row.querySelector('.league').value.trim();
        const teamSelect = row.querySelector('.team');
        teamSelect.innerHTML = '<option value="">Loading...</option>';
        if (!sport || !league) {
            teamSelect.innerHTML = '<option value="">Set sport + league</option>';
            return;
        }
        try {
            const response = await fetch(`${apiBase}&api=teams&sport=${encodeURIComponent(sport)}&league=${encodeURIComponent(league)}`);
            const data = await response.json();
            const teams = Array.isArray(data.teams) ? data.teams : [];
            teamSelect.innerHTML = '<option value="">Choose team</option>';
            teams.forEach((team) => {
                const option = document.createElement('option');
                option.value = team.id || '';
                option.textContent = team.name || team.id || '';
                option.dataset.name = team.name || '';
                option.dataset.abbr = team.abbr || '';
                if ((preferTeamId && team.id === preferTeamId) ||
                    (!preferTeamId && preferTeamName && (team.name || '').toLowerCase() === preferTeamName.toLowerCase()) ||
                    (!preferTeamId && preferTeamAbbr && (team.abbr || '').toLowerCase() === preferTeamAbbr.toLowerCase())) {
                    option.selected = true;
                }
                teamSelect.appendChild(option);
            });
        } catch (error) {
            teamSelect.innerHTML = '<option value="">Failed to load teams</option>';
        }
    }

    function addRow(mapping) {
        const data = Object.assign({
            sport: '',
            league: '',
            team_id: '',
            team_name: '',
            team_abbr: '',
            playlist: playlists[0] || '',
            pregame_minutes: 60,
            game_length_hours: 3.0,
            postgame_buffer_minutes: 30
        }, mapping || {});

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><input class="form-control form-control-sm sport" type="text" value="${(data.sport || '').replace(/"/g, '&quot;')}"></td>
            <td><input class="form-control form-control-sm league" type="text" value="${(data.league || '').replace(/"/g, '&quot;')}"></td>
            <td>
                <div style="display:flex; gap:4px;">
                    <select class="form-control form-control-sm team"><option value="">Choose team</option></select>
                    <button type="button" class="btn btn-outline-secondary btn-sm load-teams">Load</button>
                </div>
            </td>
            <td></td>
            <td><input class="form-control form-control-sm pregame" type="number" min="0" value="${Number(data.pregame_minutes || 60)}"></td>
            <td><input class="form-control form-control-sm gamehours" type="number" min="0.5" step="0.5" value="${Number(data.game_length_hours || 3.0)}"></td>
            <td><input class="form-control form-control-sm postgame" type="number" min="0" value="${Number(data.postgame_buffer_minutes || 30)}"></td>
            <td><button type="button" class="btn btn-outline-danger btn-sm remove-row">Remove</button></td>
        `;

        tr.children[3].appendChild(makePlaylistSelect(data.playlist || ''));
        body.appendChild(tr);

        tr.querySelector('.remove-row').addEventListener('click', () => {
            tr.remove();
        });

        tr.querySelector('.load-teams').addEventListener('click', () => {
            loadTeamsForRow(tr, '', '', '');
        });

        if (data.sport && data.league) {
            loadTeamsForRow(tr, data.team_id || '', data.team_name || '', data.team_abbr || '');
        }
    }

    addBtn.addEventListener('click', () => addRow({}));

    form.addEventListener('submit', (event) => {
        const rows = [];
        body.querySelectorAll('tr').forEach((row) => {
            const sport = row.querySelector('.sport').value.trim();
            const league = row.querySelector('.league').value.trim();
            const playlist = row.querySelector('.playlist').value.trim();
            const teamSelect = row.querySelector('.team');
            const selected = teamSelect.options[teamSelect.selectedIndex] || null;
            const teamId = selected ? selected.value : '';
            const teamName = selected ? (selected.dataset.name || selected.textContent || '') : '';
            const teamAbbr = selected ? (selected.dataset.abbr || '') : '';
            if (!sport || !league || !playlist) {
                return;
            }
            rows.push({
                sport,
                league,
                playlist,
                team_id: teamId,
                team_name: teamName.trim(),
                team_abbr: teamAbbr.trim(),
                pregame_minutes: Math.max(0, parseInt(row.querySelector('.pregame').value || '60', 10)),
                game_length_hours: Math.max(0.5, parseFloat(row.querySelector('.gamehours').value || '3')),
                postgame_buffer_minutes: Math.max(0, parseInt(row.querySelector('.postgame').value || '30', 10))
            });
        });
        mappingsInput.value = JSON.stringify(rows);
    });

    if (Array.isArray(initialMappings) && initialMappings.length > 0) {
        initialMappings.forEach((row) => addRow(row));
    } else {
        addRow({});
    }
})();
</script>
