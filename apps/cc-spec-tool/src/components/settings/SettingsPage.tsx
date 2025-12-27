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
import { translations } from "../../types/viewer";
import { Icons } from "../icons/Icons";

// 翻译对象类型
type TranslationMap = typeof translations.zh;

interface SettingsPageProps {
  onClose: () => void;
  isDarkMode: boolean;
  onOpenModelManager?: () => void;
  t: TranslationMap;
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

export function SettingsPage({ onClose, isDarkMode, onOpenModelManager, t }: SettingsPageProps) {
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
      setMessage(t.settingsSaved);
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

  // Styles based on theme
  const cardClass = isDarkMode
    ? "bg-slate-800 border-slate-700 shadow-sm"
    : "bg-white border-slate-200 shadow-sm";

  const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
  const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";
  const borderClass = isDarkMode ? "border-slate-700" : "border-slate-200";
  const inputClass = `w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:ring-2 focus:ring-opacity-50 transition-all ${isDarkMode
    ? "bg-slate-900 border-slate-700 text-slate-100 focus:ring-purple-500 focus:border-purple-500"
    : "bg-white border-slate-200 text-slate-800 focus:ring-blue-500 focus:border-blue-500"
    }`;
  const checkboxClass = "rounded text-blue-600 focus:ring-blue-500 h-4 w-4 transform translate-y-0.5";

  return (
    <div className="flex flex-col gap-8 pb-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`text-2xl font-bold ${textPrimary}`}>{t.settingsTitle}</h1>
          <p className={`text-sm mt-1 ${textSecondary}`}>{t.settingsDesc}</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${isDarkMode ? "bg-transparent border-slate-600 text-slate-300 hover:bg-slate-800" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"}`}
          >
            {t.goBack}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className={`px-4 py-2 rounded-xl text-sm font-semibold text-white shadow-md transition-all active:scale-95 ${saving ? "bg-slate-500 cursor-wait" : "bg-[var(--accent)] hover:brightness-110"}`}
          >
            {saving ? t.savingSettings : t.saveSettings}
          </button>
        </div>
      </div>

      {message && (
        <div className={`p-3 rounded-xl text-sm font-medium ${message.includes("Failed") ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"}`}>
          {message}
        </div>
      )}

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Left Column */}
        <div className="flex flex-col gap-6">
          {/* Concurrency Card */}
          {concurrency && (
            <div className={`p-6 rounded-2xl border ${cardClass}`}>
              <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>{t.concurrencyStatus}</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className={`p-3 rounded-xl border ${isDarkMode ? "bg-slate-900/50 border-slate-700" : "bg-slate-50 border-slate-100"}`}>
                  <div className="text-xs font-medium text-slate-500 mb-1">CC (Claude)</div>
                  <div className={`text-xl font-bold ${textPrimary}`}>{concurrency.cc_running}/{concurrency.cc_max}</div>
                  {concurrency.cc_queued > 0 && <div className="text-xs text-amber-500 font-medium">+{concurrency.cc_queued} {t.queued}</div>}
                </div>
                <div className={`p-3 rounded-xl border ${isDarkMode ? "bg-slate-900/50 border-slate-700" : "bg-slate-50 border-slate-100"}`}>
                  <div className="text-xs font-medium text-slate-500 mb-1">CX (Codex)</div>
                  <div className={`text-xl font-bold ${textPrimary}`}>{concurrency.cx_running}/{concurrency.cx_max}</div>
                  {concurrency.cx_queued > 0 && <div className="text-xs text-amber-500 font-medium">+{concurrency.cx_queued} {t.queued}</div>}
                </div>
                <div className={`p-3 rounded-xl border ${isDarkMode ? "bg-slate-900/50 border-slate-700" : "bg-slate-50 border-slate-100"}`}>
                  <div className="text-xs font-medium text-slate-500 mb-1">{t.total}</div>
                  <div className={`text-xl font-bold ${concurrency.total_running >= concurrency.total_max ? "text-red-500" : textPrimary}`}>
                    {concurrency.total_running}/{concurrency.total_max}
                  </div>
                </div>
              </div>
              {concurrency.total_running >= concurrency.total_max && (
                <div className="mt-4 text-xs font-medium text-red-500 flex items-center gap-2">
                  <Icons.Warn /> {t.concurrencyLimitReached}
                </div>
              )}
            </div>
          )}

          {/* Claude Settings */}
          <div className={`p-6 rounded-2xl border ${cardClass}`}>
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>{t.claudeConfig}</h3>
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label className={`text-sm font-medium ${textPrimary}`}>{t.execPath}</label>
                <div className="flex gap-4">
                  <label className={`flex items-center gap-2 text-sm cursor-pointer ${textSecondary}`}>
                    <input type="radio" className={checkboxClass} checked={settings.claude.path === "auto"} onChange={() => updateClaude("path", "auto")} />
                    {t.autoDetect}
                  </label>
                  <label className={`flex items-center gap-2 text-sm cursor-pointer ${textSecondary}`}>
                    <input type="radio" className={checkboxClass} checked={settings.claude.path === "custom"} onChange={() => updateClaude("path", "custom")} />
                    {t.customPath}
                  </label>
                </div>
                {settings.claude.path === "custom" && (
                  <input
                    type="text"
                    value={settings.claude.custom_path || ""}
                    onChange={(e) => updateClaude("custom_path", e.target.value)}
                    placeholder={t.enterClaudePath}
                    className={inputClass}
                  />
                )}
              </div>
              <div>
                <label className={`block text-sm font-medium mb-2 ${textPrimary}`}>{t.maxConcurrent}</label>
                <div className="flex items-center gap-4">
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={settings.claude.max_concurrent}
                    onChange={(e) => updateClaude("max_concurrent", parseInt(e.target.value) || 1)}
                    className={`${inputClass} w-24`}
                  />
                  <span className="text-xs text-slate-500">{t.suggestedValue}</span>
                </div>
              </div>
            </div>
          </div>

          {/* UI Settings */}
          <div className={`p-6 rounded-2xl border ${cardClass}`}>
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>{t.uiDisplay}</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={`block text-sm font-medium mb-2 ${textPrimary}`}>{t.theme}</label>
                <select
                  value={settings.ui.theme}
                  onChange={(e) => updateUi("theme", e.target.value)}
                  className={inputClass}
                >
                  <option value="system">{t.followSystem}</option>
                  <option value="dark">{t.darkTheme}</option>
                  <option value="light">{t.lightTheme}</option>
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-2 ${textPrimary}`}>{t.languageLabel}</label>
                <select
                  value={settings.ui.language}
                  onChange={(e) => updateUi("language", e.target.value)}
                  className={inputClass}
                >
                  <option value="zh-CN">{t.chineseSimplified}</option>
                  <option value="en-US">{t.englishLang}</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="flex flex-col gap-6">
          {/* Codex Settings */}
          <div className={`p-6 rounded-2xl border ${cardClass}`}>
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>{t.codexConfig}</h3>
            <div>
              <div className="flex justify-between mb-2">
                <label className={`text-sm font-medium ${textPrimary}`}>{t.maxConcurrent}</label>
                <span className={`text-sm font-bold ${isDarkMode ? "text-purple-400" : "text-blue-600"}`}>{settings.codex.max_concurrent}</span>
              </div>
              <input
                type="range"
                min={1}
                max={10}
                value={settings.codex.max_concurrent}
                onChange={(e) => updateCodex("max_concurrent", parseInt(e.target.value))}
                className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer dark:bg-slate-700 accent-blue-600"
              />
              <div className="flex justify-between mt-1 text-xs text-slate-500">
                <span>1</span>
                <span>10</span>
              </div>
            </div>
          </div>

          {/* Index Settings */}
          <div className={`p-6 rounded-2xl border ${cardClass}`}>
            <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>{t.indexSettings}</h3>
            <div className="flex flex-col gap-3">
              <label className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${settings.index.enabled ? (isDarkMode ? "bg-purple-900/20 border-purple-500/50" : "bg-blue-50 border-blue-200") : borderClass}`}>
                <input type="checkbox" className={checkboxClass} checked={settings.index.enabled} onChange={(e) => updateIndex("enabled", e.target.checked)} />
                <span className={`text-sm font-medium ${textPrimary}`}>{t.enableMultiLevelIndex}</span>
              </label>
              <label className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${settings.index.auto_update ? (isDarkMode ? "bg-purple-900/20 border-purple-500/50" : "bg-blue-50 border-blue-200") : borderClass}`}>
                <input type="checkbox" className={checkboxClass} checked={settings.index.auto_update} onChange={(e) => updateIndex("auto_update", e.target.checked)} />
                <span className={`text-sm font-medium ${textPrimary}`}>{t.autoUpdateIndex}</span>
              </label>
            </div>
          </div>

          {/* Translation Settings - Entry Card */}
          <div className={`p-6 rounded-2xl border ${cardClass}`}>
            <div className="flex items-center justify-between mb-4">
              <h3 className={`text-lg font-semibold ${textPrimary}`}>{t.translationModel}</h3>
              <div className={`px-2 py-0.5 rounded text-xs font-semibold ${translationStatus?.downloaded ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300" : "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400"}`}>
                {translationStatus?.downloaded ? (translationStatus?.loaded ? t.loaded : t.downloaded) : t.notDownloaded}
              </div>
            </div>

            <div className="space-y-4">
              <div className={`text-xs space-y-1 ${textSecondary}`}>
                <div className="flex justify-between"><span>{t.currentModelLabel}:</span> <span className="font-mono">{translationStatus?.model_version || t.noneModel}</span></div>
                <div className="flex justify-between"><span>{t.fileSize}:</span> <span className="font-mono">{formatBytes(translationStatus?.model_size)}</span></div>
                <div className="flex justify-between"><span>{t.cacheEntriesLabel}:</span> <span className="font-mono">{translationCache?.cached_count ?? 0}</span></div>
              </div>

              <p className={`text-xs ${textSecondary}`}>
                {t.translationModelDesc}
              </p>

              {translationError && (
                <div className="text-xs text-red-500 bg-red-50 dark:bg-red-900/10 p-2 rounded">
                  {translationError}
                </div>
              )}

              <button
                onClick={onOpenModelManager}
                className="w-full px-4 py-3 rounded-xl text-sm font-semibold text-white shadow-md transition-all hover:scale-[1.02] active:scale-[0.98] bg-[var(--accent)] hover:brightness-110"
              >
                <div className="flex items-center justify-center gap-2">
                  <Icons.Download />
                  <span>{t.openModelManager}</span>
                </div>
              </button>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={loadTranslationStatus}
                  className={`flex-1 px-3 py-1.5 rounded-lg text-xs border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
                >
                  {t.refreshStatus}
                </button>
                <button
                  onClick={handleClearTranslationCache}
                  className={`flex-1 px-3 py-1.5 rounded-lg text-xs border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
                >
                  {t.clearCache}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
