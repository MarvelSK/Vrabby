#!/usr/bin/env node

const {spawn} = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');
require('dotenv').config();

const apiDir = path.join(__dirname, '..', 'apps', 'api');
const isWindows = os.platform() === 'win32';

// Get API port from environment or use default
const apiPort = process.env.API_PORT || 8080;

// Determine Python path in venv
const venvPython = isWindows
    ? path.join(apiDir, '.venv', 'Scripts', 'python.exe')
    : path.join(apiDir, '.venv', 'bin', 'python');

// Fallback to system python if venv python is missing
let pythonPath = venvPython;
if (!fs.existsSync(pythonPath)) {
    console.warn('\n[API] Virtualenv Python not found at:', pythonPath);
    // Prefer stable CPython versions first to avoid incompatibilities (e.g., 3.14 dev)
    const candidates = isWindows
        ? ['py -3.12', 'py -3.11', 'py -3.10', 'python3.12', 'python3.11', 'python3.10', 'python', 'py -3']
        : ['python3.12', 'python3.11', 'python3.10', 'python3', 'python'];
    for (const cmd of candidates) {
        try {
            // Try to run a no-op to verify the interpreter
            const {execSync} = require('child_process');
            execSync(`${cmd} -c "import sys; print(sys.version)"`, {stdio: 'ignore', shell: isWindows});
            pythonPath = cmd;
            console.warn(`[API] Falling back to system Python: ${cmd}`);
            break;
        } catch (_) {
            // try next
        }
    }
}

// Report and validate Python version
try {
    const { execSync } = require('child_process');
    const verStr = execSync(`${pythonPath} -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"`, {
        encoding: 'utf8',
        stdio: 'pipe',
        shell: isWindows,
        cwd: apiDir,
    }).trim();
    const parts = verStr.split('.').map(n => parseInt(n, 10));
    const major = parts[0] || 0;
    const minor = parts[1] || 0;
    console.log(`[API] Using Python ${verStr}`);
    if (major === 3 && minor >= 14) {
        console.warn('[API] Detected Python >= 3.14 which may be unsupported by some dependencies.');
        console.warn('[API] It is recommended to create a 3.12 virtualenv and re-run:');
        if (isWindows) {
            console.warn('      py -3.12 -m venv apps\\api\\.venv');
            console.warn('      apps\\api\\.venv\\Scripts\\pip install -r apps\\api\\requirements.txt');
        } else {
            console.warn('      python3.12 -m venv apps/api/.venv');
            console.warn('      apps/api/.venv/bin/pip install -r apps/api/requirements.txt');
        }
    }
} catch (e) {
    // If we cannot determine the version, proceed; spawn will error if truly broken
}

// Preflight: ensure core Python deps are installed (uvicorn, pydantic, pydantic_core)
let uvicornOk = false;
try {
    const { execSync } = require('child_process');
    const checkCmd = `${pythonPath} -c "import importlib;\nfor m in ['uvicorn','pydantic','pydantic_core']:\n    importlib.import_module(m)\nprint('OK')"`;
    execSync(checkCmd, { stdio: 'pipe', shell: isWindows, cwd: apiDir });
    uvicornOk = true;
} catch (e) {
    console.warn('[API] Installing missing Python packages...');
    try {
        // Prefer venv pip if available
        const pipPath = isWindows
            ? path.join(apiDir, '.venv', 'Scripts', 'pip.exe')
            : path.join(apiDir, '.venv', 'bin', 'pip');
        if (fs.existsSync(pipPath)) {
            require('child_process').execSync(`"${pipPath}" install -r requirements.txt`, { cwd: apiDir, stdio: 'inherit' });
        } else {
            require('child_process').execSync(`${pythonPath} -m pip install -r requirements.txt`, { cwd: apiDir, stdio: 'inherit', shell: isWindows });
        }
        // Re-check after installation
        try {
            const { execSync } = require('child_process');
            const checkCmd = `${pythonPath} -c "import importlib; importlib.import_module('uvicorn'); print('OK')"`;
            execSync(checkCmd, { stdio: 'pipe', shell: isWindows, cwd: apiDir });
            uvicornOk = true;
        } catch {
            uvicornOk = false;
        }
        console.log('[API] Python packages installed.');
    } catch (err) {
        console.warn('[API] Failed to auto-install requirements. You may need to install manually.');
        uvicornOk = false;
    }
}

console.log(`Starting API server on http://localhost:${apiPort}...`);

function spawnApi(py) {
    const debugEnv = String(process.env.DEBUG || '').trim().toLowerCase();
    const debugEnabled = ['1','true','yes','on'].includes(debugEnv);
    const logLevel = debugEnabled ? 'info' : 'warning';
    const childEnv = {
        ...process.env,
        API_PORT: apiPort.toString(),
        // Disable DB migrations by default in dev unless explicitly enabled
        DB_MIGRATIONS_ON_STARTUP: (process.env.DB_MIGRATIONS_ON_STARTUP ?? '0'),
    };
    return spawn(
        py,
        ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', apiPort.toString(), '--log-level', logLevel],
        {
            cwd: apiDir,
            stdio: 'inherit',
            shell: isWindows,
            env: childEnv
        }
    );
}

let apiProcess = spawnApi(pythonPath);

apiProcess.on('error', (error) => {
    console.error('\nFailed to start API server');
    console.error('Error:', error.message);
    console.error('\nHow to fix:');
    console.error('   1. Check if Python is installed and on PATH');
    console.error('   2. Prefer Python 3.12 for development to avoid dependency issues.');
    console.error('   3. Ensure virtualenv exists or install requirements:');
    if (isWindows) {
        console.error('      apps\\api\\.venv\\Scripts\\pip install -r apps\\api\\requirements.txt');
        console.error('      Or create venv with: py -3.12 -m venv apps\\api\\.venv');
    } else {
        console.error('      cd apps/api && .venv/bin/pip install -r requirements.txt');
        console.error('      Or create venv with: python3.12 -m venv .venv');
    }
    console.error('\n   4. If it exists but still fails:');
    console.error('      pnpm run clean');
    console.error('      pnpm install');
    console.error('\n   5. Check if port is available:');
    console.error(`      lsof -i :${apiPort} (Mac/Linux)`);
    console.error(`      netstat -ano | findstr :${apiPort} (Windows)`);
    process.exit(1);
});

apiProcess.on('exit', (code) => {
    if (code !== 0 && code !== null) {
        console.error(`API server exited with code ${code}`);
        // Only show uvicorn hint if uvicorn wasn't importable during preflight
        if (!uvicornOk) {
            console.error('Module uvicorn not found. Install dependencies:');
            if (isWindows) {
                console.error('  apps\\api\\.venv\\Scripts\\pip install -r apps\\api\\requirements.txt');
            } else {
                console.error('  cd apps/api && .venv/bin/pip install -r requirements.txt');
            }
        } else {
            console.error('The API crashed during startup. Check logs above for the real error (e.g., database connectivity/migrations).');
            console.error('Tip: set DB_MIGRATIONS_ON_STARTUP=0 to skip DB migrations in development.');
        }
        process.exit(code);
    }
});