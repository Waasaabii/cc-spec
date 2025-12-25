// 翻译模型信息（来自 HuggingFace API）
export interface TranslationModelInfo {
  id: string;
  name: string;
  description: string;
  size: number;
  downloads: number;
  likes: number;
  tags: string[];
  supports_en_zh: boolean;
  is_recommended: boolean;
}

// 本地模型状态
export type ModelState =
  | "NotDownloaded"
  | "Downloading"
  | "Downloaded"
  | "Loading"
  | "Loaded"
  | { Error: string };

// 本地模型记录
export interface LocalModelRecord {
  id: string;
  name: string;
  size: number;
  state: ModelState;
  path: string | null;
  downloaded_at: string | null;
  last_used_at: string | null;
  files: ModelFileStatus[];
}

// 模型文件状态
export interface ModelFileStatus {
  name: string;
  exists: boolean;
  size: number | null;
  expected_size: number | null;
}

// 下载进度（字节级别）
export interface DownloadProgress {
  model_id: string;
  status: string;
  current_file: string;
  current_file_index: number;
  total_files: number;
  file_downloaded: number;
  file_total: number;
  total_downloaded: number;
  total_size: number;
  speed_bps: number;
  eta_seconds: number | null;
  progress_percent: number;
}

// 资源占用信息
export interface ResourceUsage {
  memory_mb: number;
  cpu_percent: number;
  model_loaded: boolean;
  active_model_id: string | null;
  cache_entries: number;
  cache_size_bytes: number;
  device: string; // "CPU" | "CUDA" | "Metal"
}

// 模型管理器状态
export interface ModelManagerStatus {
  available_models: TranslationModelInfo[];
  local_models: LocalModelRecord[];
  active_model_id: string | null;
  resource_usage: ResourceUsage;
  last_updated: string;
}

// 下载完成事件
export interface TranslationDownloadCompleted {
  success: boolean;
  model_id?: string;
  error?: string;
  path?: string;
  total_size?: number;
}

// 兼容旧类型
export type TranslationModelFileStatus = ModelFileStatus;

export type TranslationModelStatus = {
  downloaded: boolean;
  model_path: string | null;
  model_size: number | null;
  model_version: string | null;
  files: TranslationModelFileStatus[];
  ready: boolean;
  loaded: boolean;
};

export type TranslationDownloadProgress = DownloadProgress;

export type TranslationCacheStats = {
  cached_count: number;
  model_ready: boolean;
  model_loaded: boolean;
};

// 工具函数
export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export function formatSpeed(bps: number): string {
  return `${formatBytes(bps)}/s`;
}

export function formatEta(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return "--";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export function getModelStateText(state: ModelState): string {
  if (typeof state === "string") {
    switch (state) {
      case "NotDownloaded": return "未下载";
      case "Downloading": return "下载中";
      case "Downloaded": return "已下载";
      case "Loading": return "加载中";
      case "Loaded": return "已加载";
      default: return state;
    }
  }
  if ("Error" in state) {
    return `错误: ${state.Error}`;
  }
  return "未知";
}

export function getModelStateColor(state: ModelState): string {
  if (typeof state === "string") {
    switch (state) {
      case "NotDownloaded": return "text-slate-500";
      case "Downloading": return "text-blue-500";
      case "Downloaded": return "text-green-500";
      case "Loading": return "text-amber-500";
      case "Loaded": return "text-emerald-500";
      default: return "text-slate-500";
    }
  }
  return "text-red-500";
}
