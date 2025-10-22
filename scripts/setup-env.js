#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const net = require('net');

const rootDir = path.join(__dirname, '..');
const envFile = path.join(rootDir, '.env');
const webEnvFile = path.join(rootDir, 'apps', 'web', '.env.local');

// Default ports
const DEFAULT_API_PORT = 8080;
const DEFAULT_WEB_PORT = 3000;

// Robust check: consider a port unavailable if a TCP connection succeeds
// This avoids false positives when another process bound the port with SO_REUSEPORT
function isPortAvailable(port) {
    const tryConnect = (host) => new Promise((resolve) => {
        const socket = net.connect({port, host});
        let settled = false;

        const finish = (available) => {
            if (settled) return;
            settled = true;
            try {
                socket.destroy();
            } catch (_) {
            }
            resolve(available);
        };

        socket.once('connect', () => finish(false)); // Something is listening
        socket.once('error', (err) => {
            // ECONNREFUSED => nothing listening on that host
            // ETIMEDOUT/EHOSTUNREACH => treat as available for localhost checks
            finish(true);
        });
        socket.setTimeout(500, () => finish(true));
    });

    // Check both IPv4 and IPv6 localhost
    return Promise.all([
        tryConnect('127.0.0.1'),
        tryConnect('::1').catch(() => true), // ignore if IPv6 not available
    ]).then((results) => results.every(Boolean));
}

// Find available port starting from default
async function findAvailablePort(startPort) {
    let port = startPort;
    while (!(await isPortAvailable(port))) {
        port++;
    }
    return port;
}

async function setupEnvironment() {
    console.log('Setting up environment...');

    try {
        // Ensure data directory exists
        const dataDir = path.join(rootDir, 'data');
        if (!fs.existsSync(dataDir)) {
            fs.mkdirSync(dataDir, {recursive: true});
            console.log('  Created data directory');
        }

        const envExists = fs.existsSync(envFile);
        let apiPort;
        let webPort;

        if (envExists) {
            // Read existing .env and DO NOT overwrite it
            const prev = fs.readFileSync(envFile, 'utf8');
            const getVal = (key, def) => {
                const m = prev.match(new RegExp(`^${key}=(.*)$`, 'm'));
                return (m && m[1] && m[1].trim()) ? m[1].trim() : def;
            };
            apiPort = parseInt(getVal('API_PORT', String(DEFAULT_API_PORT)), 10) || DEFAULT_API_PORT;
            webPort = parseInt(getVal('WEB_PORT', String(DEFAULT_WEB_PORT)), 10) || DEFAULT_WEB_PORT;
            console.log('  Using existing .env (not modifying)');
            console.log(`  API port: ${apiPort}`);
            console.log(`  Web port: ${webPort}`);
        } else {
            // Find available ports and create .env on first run only
            apiPort = await findAvailablePort(DEFAULT_API_PORT);
            webPort = await findAvailablePort(DEFAULT_WEB_PORT);

            if (apiPort !== DEFAULT_API_PORT) {
                console.log(`  API port ${DEFAULT_API_PORT} is busy, using ${apiPort}`);
            } else {
                console.log(`  API port: ${apiPort}`);
            }

            if (webPort !== DEFAULT_WEB_PORT) {
                console.log(`  Web port ${DEFAULT_WEB_PORT} is busy, using ${webPort}`);
            } else {
                console.log(`  Web port: ${webPort}`);
            }

            // Create root .env file on first run
            const envContent = `# Auto-generated environment configuration
API_PORT=${apiPort}
WEB_PORT=${webPort}
# Debug logging (set to true/1 to enable verbose logs in backend and frontend)
DEBUG=false
# Set your Supabase Postgres URL here (required)
# Example: DATABASE_URL=postgresql://postgres.YOUR_USER:YOUR_PASSWORD@YOUR_HOST:5432/postgres?sslmode=require
# Note: You can also use postgres://… — the app will normalize it automatically
DATABASE_URL=
`;

            fs.writeFileSync(envFile, envContent);
            console.log(`  Created .env`);
        }

        // Create or update apps/web/.env.local to match chosen API port
        const desiredApiBase = `http://localhost:${apiPort}`;
        const desiredWsBase = `ws://localhost:${apiPort}`;

        // Determine debug flag from root .env (if present)
        let debugEnabledForWeb = false;
        try {
            if (fs.existsSync(envFile)) {
                const prev = fs.readFileSync(envFile, 'utf8');
                const m = prev.match(/^DEBUG=(.*)$/m);
                const raw = (m && m[1] ? m[1].trim() : 'false');
                debugEnabledForWeb = /^(1|true|yes|on)$/i.test(raw);
            }
        } catch (_) {}

        const writeEnvLocal = (content) => {
            fs.writeFileSync(webEnvFile, content);
        };

        if (!fs.existsSync(webEnvFile)) {
            const webEnvContent = `# Auto-generated environment configuration\nNEXT_PUBLIC_API_BASE=${desiredApiBase}\nNEXT_PUBLIC_WS_BASE=${desiredWsBase}\nNEXT_PUBLIC_DEBUG=${debugEnabledForWeb ? 'true' : 'false'}\n`;
            writeEnvLocal(webEnvContent);
            console.log(`  Created apps/web/.env.local`);
        } else {
            let contents = fs.readFileSync(webEnvFile, 'utf8');
            const origContents = contents;

            const setOrAdd = (key, value) => {
                const safeKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const lineRe = new RegExp(`^${safeKey}=.*$`, 'm');
                if (lineRe.test(contents)) {
                    contents = contents.replace(lineRe, `${key}=${value}`);
                } else {
                    if (!contents.endsWith('\n')) contents += '\n';
                    contents += `${key}=${value}\n`;
                }
            };

            setOrAdd('NEXT_PUBLIC_API_BASE', desiredApiBase);
            setOrAdd('NEXT_PUBLIC_WS_BASE', desiredWsBase);
            setOrAdd('NEXT_PUBLIC_DEBUG', debugEnabledForWeb ? 'true' : 'false');

            // Deduplicate these keys, keeping the last occurrence
            const keysToDedup = ['NEXT_PUBLIC_API_BASE', 'NEXT_PUBLIC_WS_BASE', 'NEXT_PUBLIC_DEBUG'];
            const lines = contents.split(/\r?\n/);
            const seen = new Set();
            const result = [];
            for (let i = lines.length - 1; i >= 0; i--) {
                const line = lines[i];
                const kvMatch = line.match(/^([A-Z0-9_]+)=/);
                if (kvMatch && keysToDedup.includes(kvMatch[1])) {
                    const key = kvMatch[1];
                    if (seen.has(key)) continue; // skip older duplicates
                    seen.add(key);
                }
                result.push(line);
            }
            contents = result.reverse().join('\n');

            if (contents !== origContents) {
                writeEnvLocal(contents);
                console.log('  Updated apps/web/.env.local to match API port');
            } else {
                console.log('  apps/web/.env.local already up to date');
            }
        }

        console.log('  Environment setup complete!');

        if (apiPort !== DEFAULT_API_PORT || webPort !== DEFAULT_WEB_PORT) {
            console.log('\n  Note: Using non-default ports');
            console.log(`     API: http://localhost:${apiPort}`);
            console.log(`     Web: http://localhost:${webPort}`);
        }

        // Return ports for use in other scripts
        return {apiPort, webPort};
    } catch (error) {
        console.error('\nFailed to setup environment');
        console.error('Error:', error.message);
        console.error('\nHow to fix:');
        console.error('   1. Check file permissions');
        console.error('   2. Ensure you have write access to the project directory');
        console.error('   3. Try running with elevated permissions if needed');
        process.exit(1);
    }
}

// If run directly
if (require.main === module) {
    setupEnvironment().catch(console.error);
}

const {execSync} = require('child_process');

// Optional port-freeing on Windows; enable by setting FREE_PORTS_ON_SETUP=true
function freePort(port) {
    try {
        const output = execSync(`netstat -ano | findstr :${port}`).toString();
        const pid = output.match(/\d+$/m)?.[0];
        if (pid) {
            console.log(`🧹 Killing process on port ${port} (PID ${pid})`);
            execSync(`taskkill /PID ${pid} /F`);
        }
    } catch (_) {
    }
}

const SHOULD_FREE = /^(1|true|yes|on)$/i.test(process.env.FREE_PORTS_ON_SETUP || '');
if (SHOULD_FREE) {
    freePort(8080);
    freePort(3000);
}

module.exports = {setupEnvironment, findAvailablePort};
