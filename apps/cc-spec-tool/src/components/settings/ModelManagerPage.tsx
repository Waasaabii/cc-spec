import { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  ModelManagerStatus,
  TranslationModelInfo,
  LocalModelRecord,
  DownloadProgress,
  ResourceUsage,
} from "../../types/translation";
import {
  formatBytes,
  formatSpeed,
  formatEta,
  getModelStateText,
  getModelStateColor,
} from "../../types/translation";
import { Icons } from "../icons/Icons";

interface ModelManagerPageProps {
  onClose: () => void;
  isDarkMode: boolean;
}

export function ModelManagerPage({ onClose, isDarkMode }: ModelManagerPageProps) {
  const [status, setStatus] = useState<ModelManagerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingHf, setLoadingHf] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<Record<string, DownloadProgress>>({});
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // 快速加载本地数据
  const loadLocalStatus = useCallback(async () => {
    try {
      setLoading(true);
      const s = await invoke<ModelManagerStatus>("get_model_manager_status");
      setStatus(s);
      setError(null);
    } catch (err) {
      setError(`加载失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  // 异步加载 HF 模型列表（乐观更新）
  const loadHfModels = useCallback(async () => {
    try {
      setLoadingHf(true);
      const models = await invoke<TranslationModelInfo[]>("list_translation_models", {
        maxSizeMb: 1024,
      });
      setStatus((prev) => prev ? { ...prev, available_models: models } : prev);
    } catch (err) {
      console.error("加载 HF 模型列表失败:", err);
    } finally {
      setLoadingHf(false);
    }
  }, []);

  // 初始化：先加载本地，再加载 HF
  useEffect(() => {
    loadLocalStatus().then(() => loadHfModels());
  }, [loadLocalStatus, loadHfModels]);

  // 定时刷新本地数据（5秒），HF 数据不自动刷新
  useEffect(() => {
    const interval = setInterval(loadLocalStatus, 5000);
    return () => clearInterval(interval);
  }, [loadLocalStatus]);

  // 监听下载进度
  useEffect(() => {
    let unlistenProgress: (() => void) | null = null;
    let unlistenCompleted: (() => void) | null = null;

    const setup = async () => {
      unlistenProgress = await listen<DownloadProgress>("translation.download.progress", (event) => {
        setDownloadProgress((prev) => ({
          ...prev,
          [event.payload.model_id]: event.payload,
        }));
      });

      unlistenCompleted = await listen<{ success: boolean; model_id: string; error?: string }>(
        "translation.download.completed",
        (event) => {
          setDownloadProgress((prev) => {
            const next = { ...prev };
            delete next[event.payload.model_id];
            return next;
          });
          setActionLoading(null);
          loadLocalStatus();
        }
      );
    };

    setup();
    return () => {
      if (unlistenProgress) unlistenProgress();
      if (unlistenCompleted) unlistenCompleted();
    };
  }, [loadLocalStatus]);

  // 下载模型
  const handleDownload = async (modelId: string) => {
    setActionLoading(modelId);
    setError(null);
    try {
      await invoke("download_model", { modelId });
    } catch (err) {
      setError(`下载失败: ${err}`);
      setActionLoading(null);
    }
  };

  // 加载模型
  const handleLoad = async (modelId: string) => {
    setActionLoading(modelId);
    setError(null);
    try {
      await invoke("load_model", { modelId });
      await loadLocalStatus();
    } catch (err) {
      setError(`加载失败: ${err}`);
    } finally {
      setActionLoading(null);
    }
  };

  // 卸载模型
  const handleUnload = async () => {
    setActionLoading("unload");
    setError(null);
    try {
      await invoke("unload_model");
      await loadLocalStatus();
    } catch (err) {
      setError(`卸载失败: ${err}`);
    } finally {
      setActionLoading(null);
    }
  };

  // 删除模型
  const handleDelete = async (modelId: string) => {
    if (!confirm(`确定要删除模型 ${modelId} 吗？`)) return;
    setActionLoading(modelId);
    setError(null);
    try {
      await invoke("delete_model", { modelId });
      await loadLocalStatus();
    } catch (err) {
      setError(`删除失败: ${err}`);
    } finally {
      setActionLoading(null);
    }
  };

  // 样式
  const cardClass = isDarkMode
    ? "bg-slate-800 border-slate-700"
    : "bg-white border-slate-200";
  const textPrimary = isDarkMode ? "text-slate-100" : "text-slate-900";
  const textSecondary = isDarkMode ? "text-slate-400" : "text-slate-500";
  const borderClass = isDarkMode ? "border-slate-700" : "border-slate-200";

  // 渲染资源监控卡片
  const renderResourceCard = (usage: ResourceUsage) => (
    <div className={`p-4 rounded-xl border ${cardClass}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className={`text-sm font-semibold ${textPrimary}`}>资源占用</h3>
        <span className={`text-xs px-2 py-0.5 rounded ${
          usage.device === "CUDA"
            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
            : "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
        }`}>
          {usage.device}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
          <div className={`text-xs ${textSecondary}`}>内存</div>
          <div className={`text-lg font-bold ${textPrimary}`}>{usage.memory_mb.toFixed(1)} MB</div>
        </div>
        <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
          <div className={`text-xs ${textSecondary}`}>CPU</div>
          <div className={`text-lg font-bold ${textPrimary}`}>{usage.cpu_percent.toFixed(1)}%</div>
        </div>
        <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
          <div className={`text-xs ${textSecondary}`}>缓存条目</div>
          <div className={`text-lg font-bold ${textPrimary}`}>{usage.cache_entries}</div>
        </div>
        <div className={`p-3 rounded-lg ${isDarkMode ? "bg-slate-900/50" : "bg-slate-50"}`}>
          <div className={`text-xs ${textSecondary}`}>缓存大小</div>
          <div className={`text-lg font-bold ${textPrimary}`}>{formatBytes(usage.cache_size_bytes)}</div>
        </div>
      </div>
      {usage.active_model_id && (
        <div className="mt-3 flex items-center justify-between">
          <span className={`text-xs ${textSecondary}`}>当前模型:</span>
          <span className="text-xs font-mono text-emerald-500">{usage.active_model_id}</span>
        </div>
      )}
    </div>
  );

  // 渲染下载进度
  const renderDownloadProgress = (progress: DownloadProgress) => (
    <div className="mt-2 space-y-1">
      <div className="flex justify-between text-xs">
        <span className={textSecondary}>
          {progress.current_file} ({progress.current_file_index}/{progress.total_files})
        </span>
        <span className={textPrimary}>{progress.progress_percent.toFixed(1)}%</span>
      </div>
      <div className="h-2 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 transition-all duration-150"
          style={{ width: `${Math.min(100, progress.progress_percent)}%` }}
        />
      </div>
      <div className="flex justify-between text-xs">
        <span className={textSecondary}>
          {formatBytes(progress.total_downloaded)} / {formatBytes(progress.total_size)}
        </span>
        <span className={textSecondary}>
          {formatSpeed(progress.speed_bps)} | ETA: {formatEta(progress.eta_seconds)}
        </span>
      </div>
    </div>
  );

  // 渲染本地模型卡片
  const renderLocalModel = (model: LocalModelRecord) => {
    const isActive = status?.active_model_id === model.id;
    const isDownloading = model.id in downloadProgress;
    const progress = downloadProgress[model.id];

    return (
      <div
        key={model.id}
        className={`p-4 rounded-xl border transition-all ${cardClass} ${
          isActive ? (isDarkMode ? "ring-2 ring-emerald-500/50" : "ring-2 ring-emerald-500/30") : ""
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className={`font-semibold truncate ${textPrimary}`}>{model.name}</h4>
              {isActive && (
                <span className="px-1.5 py-0.5 rounded text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                  运行中
                </span>
              )}
            </div>
            <p className={`text-xs mt-1 font-mono ${textSecondary}`}>{model.id}</p>
            <div className="flex items-center gap-3 mt-2">
              <span className={`text-xs ${getModelStateColor(model.state)}`}>
                {getModelStateText(model.state)}
              </span>
              <span className={`text-xs ${textSecondary}`}>{formatBytes(model.size)}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 ml-4">
            {model.state === "Downloaded" && !isActive && (
              <button
                onClick={() => handleLoad(model.id)}
                disabled={actionLoading !== null}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                {actionLoading === model.id ? "加载中..." : "加载"}
              </button>
            )}
            {isActive && (
              <button
                onClick={handleUnload}
                disabled={actionLoading !== null}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-amber-500 text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-50"
              >
                {actionLoading === "unload" ? "卸载中..." : "卸载"}
              </button>
            )}
            {!isActive && model.state !== "Downloading" && (
              <button
                onClick={() => handleDelete(model.id)}
                disabled={actionLoading !== null}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-red-500 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
              >
                删除
              </button>
            )}
          </div>
        </div>

        {isDownloading && progress && renderDownloadProgress(progress)}

        {/* 文件列表 */}
        <div className="mt-3 pt-3 border-t border-dashed border-slate-200 dark:border-slate-700">
          <div className={`text-xs font-medium mb-2 ${textSecondary}`}>文件状态</div>
          <div className="grid grid-cols-2 gap-1">
            {model.files.map((file) => (
              <div key={file.name} className="flex items-center gap-1.5 text-xs">
                {file.exists ? (
                  <span className="text-emerald-500"><Icons.Check /></span>
                ) : (
                  <span className="text-red-500"><Icons.Close className="w-3 h-3" /></span>
                )}
                <span className={textSecondary}>{file.name}</span>
                {file.size && <span className="text-slate-400">({formatBytes(file.size)})</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  // 渲染可用模型卡片
  const renderAvailableModel = (model: TranslationModelInfo) => {
    const isLocal = status?.local_models.some((m) => m.id === model.id);
    const isDownloading = model.id in downloadProgress;
    const progress = downloadProgress[model.id];

    return (
      <div
        key={model.id}
        className={`p-4 rounded-xl border ${cardClass} ${
          model.is_recommended ? (isDarkMode ? "ring-1 ring-purple-500/50" : "ring-1 ring-blue-500/30") : ""
        }`}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className={`font-semibold truncate ${textPrimary}`}>{model.name}</h4>
              {model.is_recommended && (
                <span className="px-1.5 py-0.5 rounded text-xs bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                  推荐
                </span>
              )}
              {isLocal && (
                <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                  已下载
                </span>
              )}
            </div>
            <p className={`text-xs mt-1 font-mono ${textSecondary}`}>{model.id}</p>
            <p className={`text-xs mt-1 ${textSecondary}`}>{model.description}</p>
            <div className="flex items-center gap-3 mt-2">
              <span className={`text-xs ${textSecondary}`}>{formatBytes(model.size)}</span>
              <span className={`text-xs ${textSecondary}`}>{model.downloads.toLocaleString()} 下载</span>
              {model.supports_en_zh && (
                <span className="text-xs text-emerald-500">支持中英</span>
              )}
            </div>
          </div>

          <div className="ml-4">
            {!isLocal && !isDownloading && (
              <button
                onClick={() => handleDownload(model.id)}
                disabled={actionLoading !== null}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium text-white shadow-sm transition-colors disabled:opacity-50 ${
                  isDarkMode ? "bg-purple-600 hover:bg-purple-500" : "bg-blue-600 hover:bg-blue-500"
                }`}
              >
                下载
              </button>
            )}
            {isDownloading && (
              <span className="px-3 py-1.5 text-xs text-blue-500">下载中...</span>
            )}
          </div>
        </div>

        {isDownloading && progress && renderDownloadProgress(progress)}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-6 pb-10">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`text-2xl font-bold ${textPrimary}`}>模型管理</h1>
          <p className={`text-sm mt-1 ${textSecondary}`}>
            下载、加载和管理翻译模型，监控资源占用
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => { loadLocalStatus(); loadHfModels(); }}
            disabled={loading || loadingHf}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-800`}
          >
            {loading || loadingHf ? "刷新中..." : "刷新"}
          </button>
          <button
            onClick={onClose}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-colors border ${
              isDarkMode ? "bg-transparent border-slate-600 text-slate-300 hover:bg-slate-800" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            返回设置
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="p-3 rounded-xl text-sm font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {error}
        </div>
      )}

      {loading && !status ? (
        <div className={`p-8 text-center ${textSecondary}`}>加载中...</div>
      ) : status ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左侧：资源监控 */}
          <div className="lg:col-span-1 space-y-6">
            {renderResourceCard(status.resource_usage)}

            {/* 快速操作 */}
            <div className={`p-4 rounded-xl border ${cardClass}`}>
              <h3 className={`text-sm font-semibold mb-3 ${textPrimary}`}>快速操作</h3>
              <div className="space-y-2">
                <button
                  onClick={() => invoke("clear_translation_cache")}
                  className={`w-full px-3 py-2 rounded-lg text-xs border ${borderClass} ${textSecondary} hover:bg-slate-50 dark:hover:bg-slate-700`}
                >
                  清空翻译缓存
                </button>
                {status.active_model_id && (
                  <button
                    onClick={handleUnload}
                    disabled={actionLoading !== null}
                    className="w-full px-3 py-2 rounded-lg text-xs border border-amber-500 text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-50"
                  >
                    卸载当前模型
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* 右侧：模型列表 */}
          <div className="lg:col-span-2 space-y-6">
            {/* 已下载的模型 */}
            <div>
              <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>
                本地模型 ({status.local_models.length})
              </h3>
              {status.local_models.length > 0 ? (
                <div className="space-y-3">
                  {status.local_models.map(renderLocalModel)}
                </div>
              ) : (
                <div className={`p-6 rounded-xl border ${borderClass} text-center ${textSecondary}`}>
                  暂无本地模型，请从下方列表下载
                </div>
              )}
            </div>

            {/* 可用模型 */}
            <div>
              <h3 className={`text-lg font-semibold mb-4 ${textPrimary}`}>
                可用模型 {loadingHf ? "(加载中...)" : `(${status.available_models.length})`}
              </h3>
              {loadingHf && status.available_models.length === 0 ? (
                <div className={`p-6 rounded-xl border ${borderClass} text-center ${textSecondary}`}>
                  正在从 HuggingFace 获取模型列表...
                </div>
              ) : status.available_models.length > 0 ? (
                <div className="space-y-3">
                  {status.available_models.map(renderAvailableModel)}
                </div>
              ) : (
                <div className={`p-6 rounded-xl border ${borderClass} text-center ${textSecondary}`}>
                  无法获取模型列表，请检查网络连接
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
