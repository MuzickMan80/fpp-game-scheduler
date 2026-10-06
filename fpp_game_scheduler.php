<?php
/*
 * FPP plugin page rendered via:
 *   plugin.php?plugin=fpp-game-scheduler&page=fpp_game_scheduler.php
 */

function h($value)
{
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
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

$pluginName = isset($_GET['plugin']) ? basename((string)$_GET['plugin']) : 'fpp-game-scheduler';
$pluginDir = '/home/fpp/media/plugins/' . $pluginName;
$settingsPath = '/home/fpp/media/config/plugin.' . $pluginName . '.json';
$scriptPath = $pluginDir . '/fpp_game_scheduler_sync.py';

$defaults = array(
    'fpp_url' => 'http://127.0.0.1/api/configfile/schedule.json',
    'days' => 3,
    'fpp_auth' => 'auto',
    'fpp_username' => '',
    'fpp_password' => '',
    'fpp_token' => ''
);

$settings = load_settings($settingsPath, $defaults);
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

        if (save_settings($settingsPath, $settings)) {
            $messages[] = 'Settings saved.';
        } else {
            $messages[] = 'Failed to save settings.';
        }
    } elseif ($action === 'run') {
        $runDry = isset($_POST['run_dry']);
        $runDays = max(1, (int)($_POST['run_days'] ?? $settings['days']));

        if (!file_exists($scriptPath)) {
            $messages[] = 'Sync script not found at ' . $scriptPath;
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
                '--days', escapeshellarg((string)$runDays)
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
?>

<div class="container-fluid">
    <h2>FPP Game Scheduler</h2>
    <p>Configure ESPN schedule sync settings and run updates against your local FPP schedule API.</p>

    <?php foreach ($messages as $msg): ?>
        <div class="alert alert-info" role="alert"><?php echo h($msg); ?></div>
    <?php endforeach; ?>

    <div class="row">
        <div class="col-md-7">
            <div class="fpp-card">
                <div class="fpp-card-title">Settings</div>
                <div class="fpp-card-body">
                    <form method="post">
                        <input type="hidden" name="action" value="save">

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

                        <button class="btn btn-primary" type="submit">Save Settings</button>
                    </form>
                </div>
            </div>
        </div>

        <div class="col-md-5">
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
