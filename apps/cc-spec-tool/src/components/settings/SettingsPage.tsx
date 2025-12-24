import { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { ViewerSettings, ConcurrencyStatus } from "../../types/settings";
import type {
  TranslationCacheStats,
  TranslationDownloadCompleted,
  TranslationDownloadProgress,
  TranslationModelStatus,
} from "../../types/translation";

interface SettingsPageProps {
  onClose: () => void;
  isDarkMode: boolean;
}

const defaultSettings: ViewerSettings = {
  version: 1,
  port: 38888,
  claude: { path: "auto", custom_path: null, max_concurrent: 1 },
  codex: { max_concurrent: 5 },
  index: { enabled: true, auto_update: true },
  translation: { model_downloaded: false, model_path: null, cache_enabled: true },
  database: { db_type: "none", connection_string: null },
  ui: { theme: "system", language: "zh-CN" },
};

export function SettingsPage({ onClose, isDarkMode }: SettingsPageProps) {
  const [settings, setSettings] = useState<ViewerSettings>(defaultSettings);
  const [concurrency, setConcurrency] = useState<ConcurrencyStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [translationStatus, setTranslationStatus] = useState<TranslationModelStatus | null>(null);
  const [translationCache, setTranslationCache] = useState<TranslationCacheStats | null>(null);
  const [translationProgress, setTranslationProgress] = useState<TranslationDownloadProgress | null>(null);
  const [translationDownloading, setTranslationDownloading] = useState(false);
  const [translationError, setTranslationError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    try {
      const s = await invoke<ViewerSettings>("get_settings");
      setSettings(s);
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  }, []);

  const loadConcurrency = useCallback(async () => {
    try {
      const c = await invoke<ConcurrencyStatus>("get_concurrency_status");
      setConcurrency(c);
    } catch (err) {
      console.error("Failed to load concurrency:", err);
    }
  }, []);

  const loadTranslationStatus = useCallback(async () => {
    try {
      const [status, cache] = await Promise.all([
        invoke<TranslationModelStatus>("check_translation_model"),
        invoke<TranslationCacheStats>("get_translation_cache_stats"),
      ]);
      setTranslationStatus(status);
      setTranslationCache(cache);
      setTranslationError(null);
    } catch (err) {
      setTranslationError(`Failed: ${err}`);
    }
  }, []);

  useEffect(() => {
    loadSettings();
    loadConcurrency();
    loadTranslationStatus();
    const interval = setInterval(loadConcurrency, 2000);
    return () => clearInterval(interval);
  }, [loadSettings, loadConcurrency, loadTranslationStatus]);

  useEffect(() => {
    let unlistenProgress: (() => void) | null = null;
    let unlistenCompleted: (() => void) | null = null;
    const setup = async () => {
      unlistenProgress = await listen<TranslationDownloadProgress>("translation.download.progress", (event) => {
        setTranslationProgress(event.payload);
        setTranslationDownloading(true);
      });
      unlistenCompleted = await listen<TranslationDownloadCompleted>("translation.download.completed", (event) => {
        setTranslationDownloading(false);
        setTranslationProgress(null);
        if (!event.payload.success) {
          setTranslationError(event.payload.error || "Download failed");
        }
        loadTranslationStatus();
      });
    };
    setup();
    return () => {
      if (unlistenProgress) unlistenProgress();
      if (unlistenCompleted) unlistenCompleted();
    };
  }, [loadTranslationStatus]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await invoke("set_settings", { settings });
      setMessage("Settings saved!");
      setTimeout(() => setMessage(null), 2000);
    } catch (err) {
      setMessage(`Failed: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadTranslation = async () => {
    setTranslationError(null);
    setTranslationDownloading(true);
    setTranslationProgress(null);
    try {
      await invoke("download_translation_model");
    } catch (err) {
      setTranslationError(`Download failed: ${err}`);
      setTranslationDownloading(false);
    }
  };

  const handleDeleteTranslation = async () => {
    setTranslationError(null);
    try {
      await invoke("delete_translation_model");
      await loadTranslationStatus();
    } catch (err) {
      setTranslationError(`Delete failed: ${err}`);
    }
  };

  const handleClearTranslationCache = async () => {
    setTranslationError(null);
    try {
      await invoke("clear_translation_cache");
      await loadTranslationStatus();
    } catch (err) {
      setTranslationError(`Clear failed: ${err}`);
    }
  };

  const formatBytes = (value: number | null | undefined) => {
    if (!value) return "-";
    const mb = value / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  const updateClaude = <K extends keyof typeof settings.claude>(key: K, value: typeof settings.claude[K]) => {
    setSettings((s) => ({ ...s, claude: { ...s.claude, [key]: value } }));
  };

  const updateCodex = <K extends keyof typeof settings.codex>(key: K, value: typeof settings.codex[K]) => {
    setSettings((s) => ({ ...s, codex: { ...s.codex, [key]: value } }));
  };

  const updateIndex = <K extends keyof typeof settings.index>(key: K, value: typeof settings.index[K]) => {
    setSettings((s) => ({ ...s, index: { ...s.index, [key]: value } }));
  };

  const updateUi = <K extends keyof typeof settings.ui>(key: K, value: typeof settings.ui[K]) => {
    setSettings((s) => ({ ...s, ui: { ...s.ui, [key]: value } }));
  };

  const bg = isDarkMode ? "#1e1e1e" : "#ffffff";
  const fg = isDarkMode ? "#d4d4d4" : "#1e1e1e";
  const border = isDarkMode ? "#3c3c3c" : "#e0e0e0";
  const accent = isDarkMode ? "#0e639c" : "#007acc";

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: bg, color: fg, borderRadius: 8, padding: 24, width: 500, maxHeight: "80vh", overflow: "auto", boxShadow: "0 4px 20px rgba(0,0,0,0.3)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Settings</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: fg, fontSize: 20, cursor: "pointer" }}>&times;</button>
        </div>

        {concurrency && (
          <div style={{ background: isDarkMode ? "#252526" : "#f3f3f3", padding: 12, borderRadius: 6, marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: isDarkMode ? "#888" : "#666", marginBottom: 8 }}>Concurrency Status</div>
            <div style={{ display: "flex", gap: 16, marginBottom: 8 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 11, color: isDarkMode ? "#888" : "#666" }}>CC (Claude)</span>
                <span style={{ fontWeight: 600 }}>{concurrency.cc_running}/{concurrency.cc_max}</span>
                {concurrency.cc_queued > 0 && (
                  <span style={{ fontSize: 10, color: "#f59e0b" }}>+{concurrency.cc_queued} queued</span>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 11, color: isDarkMode ? "#888" : "#666" }}>CX (Codex)</span>
                <span style={{ fontWeight: 600 }}>{concurrency.cx_running}/{concurrency.cx_max}</span>
                {concurrency.cx_queued > 0 && (
                  <span style={{ fontSize: 10, color: "#f59e0b" }}>+{concurrency.cx_queued} queued</span>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 11, color: isDarkMode ? "#888" : "#666" }}>Total</span>
                <span style={{ fontWeight: 600, color: concurrency.total_running >= concurrency.total_max ? "#ef4444" : "inherit" }}>
                  {concurrency.total_running}/{concurrency.total_max}
                </span>
              </div>
            </div>
            {concurrency.total_running >= concurrency.total_max && (
              <div style={{ fontSize: 11, color: "#ef4444", padding: "4px 8px", background: isDarkMode ? "#451a1a" : "#fef2f2", borderRadius: 4 }}>
                ⚠ Concurrency limit reached. New tasks will wait.
              </div>
            )}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <fieldset style={{ border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
            <legend style={{ fontSize: 14, fontWeight: 600 }}>Claude</legend>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="radio" checked={settings.claude.path === "auto"} onChange={() => updateClaude("path", "auto")} />
                Auto detect
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="radio" checked={settings.claude.path === "custom"} onChange={() => updateClaude("path", "custom")} />
                Custom path
              </label>
              {settings.claude.path === "custom" && (
                <input
                  type="text"
                  value={settings.claude.custom_path || ""}
                  onChange={(e) => updateClaude("custom_path", e.target.value)}
                  placeholder="Path to claude executable"
                  style={{ width: "100%", marginTop: 8, padding: 6, background: isDarkMode ? "#3c3c3c" : "#fff", border: `1px solid ${border}`, borderRadius: 4, color: fg }}
                />
              )}
            </div>
            <div>
              <label style={{ fontSize: 13 }}>Max concurrent: </label>
              <input
                type="number"
                min={1}
                max={10}
                value={settings.claude.max_concurrent}
                onChange={(e) => updateClaude("max_concurrent", parseInt(e.target.value) || 1)}
                style={{ width: 60, padding: 4, background: isDarkMode ? "#3c3c3c" : "#fff", border: `1px solid ${border}`, borderRadius: 4, color: fg }}
              />
            </div>
          </fieldset>

          <fieldset style={{ border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
            <legend style={{ fontSize: 14, fontWeight: 600 }}>Codex</legend>
            <div>
              <label style={{ fontSize: 13 }}>Max concurrent: {settings.codex.max_concurrent}</label>
              <input
                type="range"
                min={1}
                max={10}
                value={settings.codex.max_concurrent}
                onChange={(e) => updateCodex("max_concurrent", parseInt(e.target.value))}
                style={{ width: "100%", marginTop: 8 }}
              />
            </div>
          </fieldset>

          <fieldset style={{ border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
            <legend style={{ fontSize: 14, fontWeight: 600 }}>Index</legend>
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <input type="checkbox" checked={settings.index.enabled} onChange={(e) => updateIndex("enabled", e.target.checked)} />
              Enable multi-level index
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={settings.index.auto_update} onChange={(e) => updateIndex("auto_update", e.target.checked)} />
              Auto update index
            </label>
          </fieldset>

          <fieldset style={{ border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
            <legend style={{ fontSize: 14, fontWeight: 600 }}>Translation</legend>
            <div style={{ fontSize: 12, color: isDarkMode ? "#888" : "#666", marginBottom: 8 }}>
              Model: {translationStatus?.downloaded ? "Downloaded" : "Not downloaded"}
              {translationStatus?.loaded ? " (Loaded)" : ""}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: 12, color: isDarkMode ? "#888" : "#666", marginBottom: 8 }}>
              <span>Version: {translationStatus?.model_version || "-"}</span>
              <span>Size: {formatBytes(translationStatus?.model_size)}</span>
              <span>Cache: {translationCache?.cached_count ?? 0}</span>
            </div>
            {translationProgress && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: isDarkMode ? "#888" : "#666" }}>{translationProgress.message}</div>
                <div style={{ height: 6, background: border, borderRadius: 999, overflow: "hidden", marginTop: 4 }}>
                  <div style={{ width: `${Math.min(100, Math.max(0, translationProgress.progress))}%`, height: "100%", background: accent }} />
                </div>
              </div>
            )}
            {translationError && (
              <div style={{ fontSize: 12, color: "#ef4444", marginBottom: 8 }}>
                {translationError}
              </div>
            )}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <button
                onClick={loadTranslationStatus}
                style={{ padding: "6px 12px", background: "transparent", border: `1px solid ${border}`, borderRadius: 4, color: fg, cursor: "pointer", fontSize: 12 }}
              >
                Refresh
              </button>
              <button
                onClick={handleDownloadTranslation}
                disabled={translationDownloading}
                style={{ padding: "6px 12px", background: accent, border: "none", borderRadius: 4, color: "#fff", cursor: translationDownloading ? "wait" : "pointer", fontSize: 12 }}
              >
                {translationDownloading ? "Downloading..." : "Download Model"}
              </button>
              <button
                onClick={handleDeleteTranslation}
                disabled={translationDownloading}
                style={{ padding: "6px 12px", background: "transparent", border: `1px solid ${border}`, borderRadius: 4, color: fg, cursor: translationDownloading ? "wait" : "pointer", fontSize: 12 }}
              >
                Delete Model
              </button>
              <button
                onClick={handleClearTranslationCache}
                style={{ padding: "6px 12px", background: "transparent", border: `1px solid ${border}`, borderRadius: 4, color: fg, cursor: "pointer", fontSize: 12 }}
              >
                Clear Cache
              </button>
            </div>
          </fieldset>

          <fieldset style={{ border: `1px solid ${border}`, borderRadius: 6, padding: 12 }}>
            <legend style={{ fontSize: 14, fontWeight: 600 }}>UI</legend>
            <div style={{ display: "flex", gap: 16 }}>
              <div>
                <label style={{ fontSize: 13 }}>Theme: </label>
                <select
                  value={settings.ui.theme}
                  onChange={(e) => updateUi("theme", e.target.value)}
                  style={{ padding: 4, background: isDarkMode ? "#3c3c3c" : "#fff", border: `1px solid ${border}`, borderRadius: 4, color: fg }}
                >
                  <option value="system">System</option>
                  <option value="dark">Dark</option>
                  <option value="light">Light</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 13 }}>Language: </label>
                <select
                  value={settings.ui.language}
                  onChange={(e) => updateUi("language", e.target.value)}
                  style={{ padding: 4, background: isDarkMode ? "#3c3c3c" : "#fff", border: `1px solid ${border}`, borderRadius: 4, color: fg }}
                >
                  <option value="zh-CN">中文</option>
                  <option value="en-US">English</option>
                </select>
              </div>
            </div>
          </fieldset>
        </div>

        {message && (
          <div style={{ marginTop: 16, padding: 8, borderRadius: 4, background: message.includes("Failed") ? "#5a1d1d" : "#1d3d1d", color: "#fff", fontSize: 13 }}>
            {message}
          </div>
        )}

        <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end", gap: 12 }}>
          <button onClick={onClose} style={{ padding: "8px 16px", background: "transparent", border: `1px solid ${border}`, borderRadius: 4, color: fg, cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} style={{ padding: "8px 16px", background: accent, border: "none", borderRadius: 4, color: "#fff", cursor: saving ? "wait" : "pointer" }}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
