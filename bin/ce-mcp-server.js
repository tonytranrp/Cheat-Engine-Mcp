#!/usr/bin/env node
const childProcess = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const packageRoot = path.resolve(__dirname, '..');
const packageJson = JSON.parse(fs.readFileSync(path.join(packageRoot, 'package.json'), 'utf8'));
const cacheRoot = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), '.cache'), 'ce-mcp-server');
const versionRoot = path.join(cacheRoot, packageJson.version);
const venvRoot = path.join(versionRoot, 'venv');
const stampPath = path.join(versionRoot, 'install-stamp.json');

function fail(message) {
  console.error(message);
  process.exit(1);
}

function run(command, args, options = {}) {
  const result = childProcess.spawnSync(command, args, {
    stdio: 'inherit',
    windowsHide: true,
    ...options,
  });

  if (result.error) {
    return null;
  }

  if ((result.status ?? 1) !== 0) {
    process.exit(result.status ?? 1);
  }

  return result;
}

function probe(command, args) {
  const result = childProcess.spawnSync(command, args, {
    encoding: 'utf8',
    windowsHide: true,
  });

  if (result.error || result.status !== 0) {
    return null;
  }

  return (result.stdout || '').trim();
}

function findPython() {
  const candidates = [];
  if (process.env.CE_MCP_PYTHON) {
    candidates.push([process.env.CE_MCP_PYTHON, []]);
  }

  if (process.platform === 'win32') {
    candidates.push(['py', ['-3.11']]);
    candidates.push(['py', ['-3']]);
    candidates.push(['python', []]);
  } else {
    candidates.push(['python3', []]);
    candidates.push(['python', []]);
  }

  for (const [command, args] of candidates) {
    const executable = probe(command, [...args, '-c', 'import sys; print(sys.executable)']);
    if (executable) {
      return { command, args };
    }
  }

  fail('Python 3.11+ was not found. Install Python or set CE_MCP_PYTHON to a valid interpreter.');
}

function venvPythonPath() {
  return process.platform === 'win32'
    ? path.join(venvRoot, 'Scripts', 'python.exe')
    : path.join(venvRoot, 'bin', 'python');
}

function loadStamp() {
  try {
    return JSON.parse(fs.readFileSync(stampPath, 'utf8'));
  } catch {
    return null;
  }
}

function ensureRuntimeInstalled() {
  fs.mkdirSync(versionRoot, { recursive: true });

  const stamp = loadStamp();
  const venvPython = venvPythonPath();
  if (stamp && stamp.version === packageJson.version && fs.existsSync(venvPython)) {
    return venvPython;
  }

  const python = findPython();
  if (!fs.existsSync(venvPython)) {
    const result = run(python.command, [...python.args, '-m', 'venv', venvRoot]);
    if (result === null) {
      fail('Failed to create the CE MCP Python virtual environment.');
    }
  }

  const runtimePython = venvPythonPath();
  const installArgs = ['-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', packageRoot];
  const installResult = run(runtimePython, installArgs);
  if (installResult === null) {
    fail('Failed to install the CE MCP Python package into its private runtime environment.');
  }

  fs.writeFileSync(stampPath, JSON.stringify({ version: packageJson.version }, null, 2));
  return runtimePython;
}

const runtimePython = ensureRuntimeInstalled();
const child = childProcess.spawnSync(runtimePython, ['-m', 'ce_mcp_server', ...process.argv.slice(2)], {
  stdio: 'inherit',
  windowsHide: true,
  env: {
    ...process.env,
    PYTHONUTF8: '1',
  },
});

if (child.error) {
  fail(child.error.message);
}

process.exit(child.status ?? 0);
