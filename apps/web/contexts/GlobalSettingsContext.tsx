"use client";
import React, {createContext, useCallback, useContext, useEffect, useMemo, useState} from 'react';
import { logger } from "@/lib/logger";

export type GlobalAISettings = {
    default_cli: string;
    cli_settings: {
        [key: string]: {
            model?: string;
        };
    };
};

type GlobalSettingsCtx = {
    settings: GlobalAISettings;
    setSettings: React.Dispatch<React.SetStateAction<GlobalAISettings>>;
    refresh: () => Promise<void>;
};

const defaultSettings: GlobalAISettings = {
    default_cli: 'claude',
    cli_settings: {},
};

const Ctx = createContext<GlobalSettingsCtx | null>(null);

export function useGlobalSettings() {
    const ctx = useContext(Ctx);
    if (!ctx) throw new Error('useGlobalSettings must be used within GlobalSettingsProvider');
    return ctx;
}

export default function GlobalSettingsProvider({children}: { children: React.ReactNode }) {
    // Do not default to localhost when not configured. This avoids noisy errors when API is not running.
    const API_BASE = process.env.NEXT_PUBLIC_API_BASE;
    const [settings, setSettings] = useState<GlobalAISettings>(defaultSettings);

    const refresh = useCallback(async () => {
        if (!API_BASE) {
            // API not configured; skip fetch silently.
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/api/settings/global`);
            if (res.ok) {
                const s = await res.json();
                setSettings(s);
            }
        } catch (e) {
            // Log once without throwing (only in debug mode)
            logger.warn('Failed to refresh global settings', e as any);
        }
    }, [API_BASE]);

    // Load once on mount
    useEffect(() => {
        refresh();
    }, [refresh]);

    const value = useMemo(() => ({settings, setSettings, refresh}), [settings, refresh]);

    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

