#!/usr/bin/env node
/**
 * Kill processes on ports 3000 and 8080 (cross-platform)
 */
const { execSync } = require("child_process");

const ports = [3000, 8080];

ports.forEach((port) => {
    try {
        console.log(`🧹 Checking port ${port}...`);
        if (process.platform === "win32") {
            // Windows
            const cmd = `for /f "tokens=5" %a in ('netstat -ano ^| findstr :${port}') do taskkill /F /PID %a`;
            execSync(cmd, { stdio: "ignore" });
        } else {
            // macOS / Linux
            execSync(`fuser -k ${port}/tcp || lsof -ti:${port} | xargs kill -9`, { stdio: "ignore" });
        }
        console.log(`✅ Port ${port} cleared.`);
    } catch {
        console.log(`ℹ️ Port ${port} was free.`);
    }
});
