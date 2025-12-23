// hooks/useSettings.ts - 设置管理 Hook

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

export interface ClaudeSettings {
    path: string;
    custom_path?: string;
    max_concurrent: number;
}

export interface CodexSettings {
    max_concurrent: number;
}

export interface IndexSettings {
    enabled: boolean;
    auto_update: boolean;
}

export interface TranslationSettings {
    model_downloaded: boolean;
    model_path?: string;
    cache_enabled: boolean;
}

export interface DatabaseSettings {
    db_type: string;
    connection_string?: string;
}

export interface UiSettings {
    theme: string;
    language: string;
}

export interface ViewerSettings {
    version: number;
    port: number;
    claude: ClaudeSettings;
    codex: CodexSettings;
    index: IndexSettings;
    translation: TranslationSettings;
    database: DatabaseSettings;
    ui: UiSettings;
}

export interface ConcurrencyStatus {
    cc_running: number;
    cx_running: number;
    cc_max: number;
    cx_max: number;
    cc_queued: number;
    cx_queued: number;
    total_running: number;
    total_max: number;
}

const defaultSettings: ViewerSettings = {
    version: 1,
    port: 38888,
    claude: {
        path: "auto",
        max_concurrent: 1,
    },
    codex: {
        max_concurrent: 5,
    },
    index: {
        enabled: true,
        auto_update: false,
    },
    translation: {
        model_downloaded: false,
        cache_enabled: true,
    },
    database: {
        db_type: "docker",
    },
    ui: {
        theme: "system",
        language: "zh-CN",
    },
};

export function useSettings() {
    const [settings, setSettings] = useState<ViewerSettings>(defaultSettings);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [concurrency, setConcurrency] = useState<ConcurrencyStatus>({
        cc_running: 0,
        cx_running: 0,
        cc_max: 1,
        cx_max: 5,
        cc_queued: 0,
        cx_queued: 0,
        total_running: 0,
        total_max: 6,
    });

    // 加载设置
    const loadSettings = useCallback(async () => {
        try {
            const result = await invoke<ViewerSettings>("get_settings");
            setSettings({ ...defaultSettings, ...result });
            setError(null);
        } catch (err) {
            setError(String(err));
        } finally {
            setLoading(false);
        }
    }, []);

    // 保存设置
    const saveSettings = useCallback(async (newSettings: Partial<ViewerSettings>) => {
        const merged = { ...settings, ...newSettings };
        try {
            await invoke("set_settings", { settings: merged });
            setSettings(merged);
            setError(null);
            return true;
        } catch (err) {
            setError(String(err));
            return false;
        }
    }, [settings]);

    // 更新单个设置项
    const updateSetting = useCallback(<K extends keyof ViewerSettings>(
        key: K,
        value: ViewerSettings[K]
    ) => {
        return saveSettings({ [key]: value } as Partial<ViewerSettings>);
    }, [saveSettings]);

    // 加载并发状态
    const loadConcurrency = useCallback(async () => {
        try {
            const status = await invoke<ConcurrencyStatus>("get_concurrency_status");
            setConcurrency(status);
        } catch {
            // 忽略错误
        }
    }, []);

    // 初始化加载
    useEffect(() => {
        loadSettings();
    }, [loadSettings]);

    // 定期刷新并发状态
    useEffect(() => {
        loadConcurrency();
        const interval = setInterval(loadConcurrency, 2000);
        return () => clearInterval(interval);
    }, [loadConcurrency]);

    return {
        settings,
        loading,
        error,
        concurrency,
        saveSettings,
        updateSetting,
        reloadSettings: loadSettings,
        reloadConcurrency: loadConcurrency,
    };
}
