import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Icons } from "../icons/Icons";
import type { ArtifactEntry, ArtifactRoot, TextPreview } from "../../types/artifacts";
import type { Theme, translations } from "../../types/viewer";

type ProjectArtifactsPanelProps = {
  theme: Theme;
  t: typeof translations["zh"];
  projectPath: string;
};

const DEFAULT_MAX_LINES = 400;

// ========== 文件类型图标 ==========
const FILE_ICONS: Record<string, string> = {
  ".md": "📝",
  ".yaml": "📋",
  ".yml": "📋",
  ".json": "📊",
  ".ts": "🔷",
  ".tsx": "🔷",
  ".js": "🟨",
  ".jsx": "🟨",
  ".py": "🐍",
  ".rs": "🦀",
  ".toml": "⚙️",
  ".txt": "📄",
};

function getFileIcon(name: string): string {
  const ext = name.lastIndexOf(".") >= 0 ? name.slice(name.lastIndexOf(".")) : "";
  return FILE_ICONS[ext.toLowerCase()] || "📄";
}

// ========== Root 分组配置 ==========
type RootGroupConfig = {
  icon: string;
  label: { zh: string; en: string };
};

const ROOT_GROUPS: Record<string, RootGroupConfig> = {
  cc_spec: { icon: "📁", label: { zh: "配置", en: "Config" } },
  changes: { icon: "📝", label: { zh: "活跃变更", en: "Changes" } },
  specs: { icon: "📄", label: { zh: "规格文档", en: "Specs" } },
  archive: { icon: "📦", label: { zh: "归档", en: "Archive" } },
};

function getRootDisplayName(rootId: string, lang: "zh" | "en"): string {
  const config = ROOT_GROUPS[rootId];
  if (config) {
    return `${config.icon} ${config.label[lang]}`;
  }
  return rootId;
}

// ========== 工具函数 ==========
function splitPath(relPath: string): string[] {
  return relPath.split("/").filter(Boolean);
}

function joinPath(parts: string[]): string {
  return parts.filter(Boolean).join("/");
}

function joinAbsAndRel(absBase: string, relPath: string): string {
  if (!absBase) return "";
  if (!relPath) return absBase;
  const sep = absBase.includes("\\") ? "\\" : "/";
  const base = absBase.replace(/[\\/]+$/, "");
  const rel = relPath.split("/").filter(Boolean).join(sep);
  return `${base}${sep}${rel}`;
}

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = unitIndex === 0 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

function isRecentlyModified(modifiedAt: string | null): boolean {
  if (!modifiedAt) return false;
  try {
    const modified = new Date(modifiedAt);
    const now = new Date();
    const diffMs = now.getTime() - modified.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    return diffHours < 24;
  } catch {
    return false;
  }
}

function formatRelativeTime(modifiedAt: string | null, lang: "zh" | "en"): string {
  if (!modifiedAt) return "-";
  try {
    const modified = new Date(modifiedAt);
    const now = new Date();
    const diffMs = now.getTime() - modified.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return lang === "zh" ? "刚刚" : "Just now";
    if (diffMins < 60) return lang === "zh" ? `${diffMins}分钟前` : `${diffMins}m ago`;
    if (diffHours < 24) return lang === "zh" ? `${diffHours}小时前` : `${diffHours}h ago`;
    if (diffDays < 7) return lang === "zh" ? `${diffDays}天前` : `${diffDays}d ago`;
    return modified.toLocaleDateString(lang === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" });
  } catch {
    return modifiedAt;
  }
}

type SortMode = "name" | "modified" | "size";

function sortEntries(entries: ArtifactEntry[], mode: SortMode): ArtifactEntry[] {
  const sorted = [...entries];
  sorted.sort((a, b) => {
    // 目录始终在前
    if (a.kind !== b.kind) {
      return a.kind === "dir" ? -1 : 1;
    }
    switch (mode) {
      case "modified":
        if (!a.modifiedAt && !b.modifiedAt) return a.name.localeCompare(b.name);
        if (!a.modifiedAt) return 1;
        if (!b.modifiedAt) return -1;
        return new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime();
      case "size":
        return b.size - a.size;
      case "name":
      default:
        return a.name.localeCompare(b.name);
    }
  });
  return sorted;
}

// ========== 主组件 ==========
export function ProjectArtifactsPanel({ theme, t, projectPath }: ProjectArtifactsPanelProps) {
  const isDark = theme === "dark";
  const lang = (t.projectTabArtifacts === "产物" ? "zh" : "en") as "zh" | "en";

  // Roots 状态
  const [roots, setRoots] = useState<ArtifactRoot[]>([]);
  const [rootsLoading, setRootsLoading] = useState(false);
  const [rootsError, setRootsError] = useState<string | null>(null);

  // 当前选中的 root 和目录
  const [rootId, setRootId] = useState<string>("cc_spec");
  const [dirPath, setDirPath] = useState<string>("");
  const [entries, setEntries] = useState<ArtifactEntry[]>([]);
  const [dirLoading, setDirLoading] = useState(false);
  const [dirError, setDirError] = useState<string | null>(null);

  // 搜索和排序
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sortMode, setSortMode] = useState<SortMode>("modified");

  // 预览状态
  const [selectedFileRel, setSelectedFileRel] = useState<string | null>(null);
  const [preview, setPreview] = useState<TextPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 侧边栏折叠状态
  const [expandedRoots, setExpandedRoots] = useState<Set<string>>(new Set(["cc_spec", "changes"]));

  const copyTimerRef = useRef<number | null>(null);
  const lastAutoSelectedRootIdRef = useRef<string | null>(null);

  const selectedRoot = useMemo(() => roots.find((r) => r.id === rootId) ?? null, [roots, rootId]);

  const breadcrumbParts = useMemo(() => splitPath(dirPath), [dirPath]);

  const currentDirAbsPath = useMemo(() => {
    if (!selectedRoot) return "";
    if (selectedRoot.kind === "file") return selectedRoot.absPath;
    return joinAbsAndRel(selectedRoot.absPath, dirPath);
  }, [dirPath, selectedRoot]);

  const selectedFileAbsPath = useMemo(() => {
    if (!selectedRoot) return "";
    if (selectedRoot.kind === "file") return selectedRoot.absPath;
    const rel = selectedFileRel ?? "";
    if (!rel) return "";
    return joinAbsAndRel(selectedRoot.absPath, rel);
  }, [selectedFileRel, selectedRoot]);

  // 过滤和排序后的条目
  const filteredEntries = useMemo(() => {
    let result = entries;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = entries.filter((e) => e.name.toLowerCase().includes(q));
    }
    return sortEntries(result, sortMode);
  }, [entries, searchQuery, sortMode]);

  const clearCopyTimer = () => {
    if (copyTimerRef.current) {
      window.clearTimeout(copyTimerRef.current);
      copyTimerRef.current = null;
    }
  };

  useEffect(() => {
    return () => clearCopyTimer();
  }, []);

  const loadRoots = useCallback(async () => {
    setRootsLoading(true);
    setRootsError(null);
    try {
      const list = await invoke<ArtifactRoot[]>("list_project_artifact_roots", { projectPath });
      lastAutoSelectedRootIdRef.current = null;
      setRoots(list);
      if (list.length > 0 && !list.some((r) => r.id === rootId)) {
        setRootId(list[0].id);
      }
    } catch (err) {
      setRootsError(err instanceof Error ? err.message : String(err));
    } finally {
      setRootsLoading(false);
    }
  }, [projectPath, rootId]);

  useEffect(() => {
    loadRoots();
  }, [loadRoots]);

  const loadDir = useCallback(async (nextRootId: string, nextDir: string) => {
    setDirLoading(true);
    setDirError(null);
    try {
      const list = await invoke<ArtifactEntry[]>("list_project_artifact_dir", {
        projectPath,
        rootId: nextRootId,
        relDir: nextDir,
      });
      setEntries(list);
    } catch (err) {
      setEntries([]);
      setDirError(err instanceof Error ? err.message : String(err));
    } finally {
      setDirLoading(false);
    }
  }, [projectPath]);

  const loadPreview = useCallback(async (nextRootId: string, relFile: string, startLine: number) => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const res = await invoke<TextPreview>("read_project_artifact_text", {
        projectPath,
        rootId: nextRootId,
        relFile,
        startLine,
        maxLines: DEFAULT_MAX_LINES,
      });
      setPreview(res);
    } catch (err) {
      setPreview(null);
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  }, [projectPath]);

  const selectRoot = useCallback(async (nextRootId: string) => {
    lastAutoSelectedRootIdRef.current = nextRootId;
    setRootId(nextRootId);
    setDirPath("");
    setEntries([]);
    setDirError(null);
    setSelectedFileRel(null);
    setPreview(null);
    setPreviewError(null);
    setSearchQuery("");

    const root = roots.find((r) => r.id === nextRootId);
    if (!root) return;
    if (!root.exists) {
      return;
    }
    if (root.kind === "file") {
      setSelectedFileRel("");
      await loadPreview(nextRootId, "", 1);
      return;
    }
    await loadDir(nextRootId, "");
  }, [loadDir, loadPreview, roots]);

  useEffect(() => {
    if (!roots.length) return;
    if (!roots.some((r) => r.id === rootId)) return;
    if (lastAutoSelectedRootIdRef.current === rootId) return;
    void selectRoot(rootId);
  }, [roots, rootId, selectRoot]);

  const navigateToDir = useCallback(async (nextDir: string) => {
    setDirPath(nextDir);
    setSelectedFileRel(null);
    setPreview(null);
    setPreviewError(null);
    setSearchQuery("");
    await loadDir(rootId, nextDir);
  }, [loadDir, rootId]);

  const openInVSCode = useCallback(async (line?: number) => {
    if (!selectedRoot) return;
    const relFile = selectedRoot.kind === "file" ? "" : (selectedFileRel ?? "");
    try {
      await invoke("open_project_artifact_in_vscode", {
        projectPath,
        rootId,
        relFile,
        line,
        col: 1,
      });
    } catch (err) {
      console.error("Failed to open in VS Code:", err);
    }
  }, [projectPath, rootId, selectedFileRel, selectedRoot]);

  const revealInExplorer = useCallback(async () => {
    if (!selectedRoot) return;
    const relPath = selectedRoot.kind === "file"
      ? ""
      : (selectedFileRel ?? dirPath);
    try {
      await invoke("reveal_project_artifact_in_file_manager", {
        projectPath,
        rootId,
        relPath,
      });
    } catch (err) {
      console.error("Failed to reveal:", err);
    }
  }, [dirPath, projectPath, rootId, selectedFileRel, selectedRoot]);

  const copyPath = useCallback(async () => {
    const text = selectedFileAbsPath || currentDirAbsPath;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearCopyTimer();
      copyTimerRef.current = window.setTimeout(() => setCopied(false), 1200);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  }, [currentDirAbsPath, selectedFileAbsPath]);

  const selectFile = useCallback(async (relFile: string) => {
    setSelectedFileRel(relFile);
    setPreview(null);
    setPreviewError(null);
    await loadPreview(rootId, relFile, 1);
  }, [loadPreview, rootId]);

  const previewLines = useMemo(() => {
    if (!preview) return [];
    if (!preview.content) return [""];
    return preview.content.split("\n");
  }, [preview]);

  const canPreview = Boolean(selectedRoot && selectedRoot.exists && (selectedRoot.kind === "file" || selectedFileRel));

  const toggleRootExpanded = (id: string) => {
    setExpandedRoots((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // ========== 渲染侧边栏树节点 ==========
  const renderSidebarTree = () => {
    return (
      <div className="flex flex-col gap-1">
        {roots.map((root) => {
          const isExpanded = expandedRoots.has(root.id);
          const isSelected = rootId === root.id;
          const displayName = getRootDisplayName(root.id, lang);

          return (
            <div key={root.id}>
              <button
                onClick={() => {
                  if (root.exists && root.kind === "dir") {
                    toggleRootExpanded(root.id);
                  }
                  void selectRoot(root.id);
                }}
                className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-2 text-sm transition-colors ${
                  isSelected
                    ? isDark
                      ? "bg-slate-700 text-white"
                      : "bg-slate-200 text-slate-900"
                    : isDark
                      ? "hover:bg-slate-800 text-slate-300"
                      : "hover:bg-slate-100 text-slate-600"
                }`}
              >
                {root.kind === "dir" && (
                  <span className={`text-xs transition-transform ${isExpanded ? "rotate-90" : ""}`}>
                    ▶
                  </span>
                )}
                <span className="flex-1 truncate">{displayName}</span>
                {!root.exists && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    isDark ? "bg-slate-800 text-slate-500" : "bg-slate-100 text-slate-400"
                  }`}>
                    {t.notGenerated || "未生成"}
                  </span>
                )}
              </button>

              {/* 子目录预览 */}
              {isExpanded && root.exists && root.kind === "dir" && isSelected && entries.length > 0 && (
                <div className="ml-6 mt-1 flex flex-col gap-0.5">
                  {entries.slice(0, 8).map((entry) => (
                    <button
                      key={entry.relPath}
                      onClick={() => {
                        if (entry.kind === "dir") {
                          void navigateToDir(entry.relPath);
                        } else {
                          void selectFile(entry.relPath);
                        }
                      }}
                      className={`text-left px-2 py-1 rounded text-xs truncate transition-colors ${
                        selectedFileRel === entry.relPath
                          ? isDark
                            ? "bg-slate-700 text-white"
                            : "bg-slate-200 text-slate-900"
                          : isDark
                            ? "hover:bg-slate-800/50 text-slate-400"
                            : "hover:bg-slate-50 text-slate-500"
                      }`}
                    >
                      {entry.kind === "dir" ? "📁" : getFileIcon(entry.name)} {entry.name}
                    </button>
                  ))}
                  {entries.length > 8 && (
                    <span className={`px-2 py-1 text-[10px] ${isDark ? "text-slate-500" : "text-slate-400"}`}>
                      +{entries.length - 8} {lang === "zh" ? "更多" : "more"}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // ========== 渲染文件列表 ==========
  const renderFileList = () => {
    if (!selectedRoot) {
      return (
        <div className={`text-center py-12 ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          {t.selectArtifactHint || "请选择一个产物目录"}
        </div>
      );
    }

    if (!selectedRoot.exists) {
      return (
        <div className={`text-center py-12 ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          {t.notGeneratedHint || "该项尚未生成或已被清理"}
        </div>
      );
    }

    if (selectedRoot.kind === "file") {
      return (
        <div className={`px-3 py-2 rounded-lg ${isDark ? "bg-slate-800/50" : "bg-slate-50"}`}>
          <div className="flex items-center gap-2">
            <span>{getFileIcon(selectedRoot.relPath)}</span>
            <span className={`text-sm font-medium ${isDark ? "text-slate-200" : "text-slate-700"}`}>
              {selectedRoot.relPath}
            </span>
          </div>
        </div>
      );
    }

    if (dirLoading) {
      return (
        <div className={`text-center py-12 ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          {t.loading || "加载中..."}
        </div>
      );
    }

    if (filteredEntries.length === 0) {
      return (
        <div className={`text-center py-12 ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          {searchQuery ? (lang === "zh" ? "未找到匹配的文件" : "No matching files") : (t.emptyFolder || "空文件夹")}
        </div>
      );
    }

    return (
      <div className="flex flex-col">
        {filteredEntries.map((entry) => {
          const isRecent = isRecentlyModified(entry.modifiedAt);
          const isFileSelected = selectedFileRel === entry.relPath;

          return (
            <button
              key={entry.relPath}
              onClick={() => {
                if (entry.kind === "dir") {
                  void navigateToDir(entry.relPath);
                } else {
                  void selectFile(entry.relPath);
                }
              }}
              className={`w-full text-left px-3 py-2 flex items-center gap-3 border-b transition-colors ${
                isFileSelected
                  ? isDark
                    ? "bg-slate-700/50 border-slate-700"
                    : "bg-blue-50 border-blue-100"
                  : isDark
                    ? "border-slate-800 hover:bg-slate-800/50"
                    : "border-slate-100 hover:bg-slate-50"
              }`}
            >
              <span className="text-base flex-shrink-0">
                {entry.kind === "dir" ? "📁" : getFileIcon(entry.name)}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium truncate ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                    {entry.name}
                  </span>
                  {isRecent && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                      isDark ? "bg-emerald-900/50 text-emerald-300" : "bg-emerald-100 text-emerald-600"
                    }`}>
                      ✨ {lang === "zh" ? "最近" : "Recent"}
                    </span>
                  )}
                </div>
              </div>
              <div className={`text-xs flex-shrink-0 text-right ${isDark ? "text-slate-500" : "text-slate-400"}`}>
                {entry.kind === "file" && (
                  <div>{formatBytes(entry.size)}</div>
                )}
                <div>{formatRelativeTime(entry.modifiedAt, lang)}</div>
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  // ========== 渲染预览区 ==========
  const renderPreview = () => {
    const fileName = selectedRoot?.kind === "file"
      ? selectedRoot.relPath
      : selectedFileRel
        ? selectedFileRel.split("/").pop() || ""
        : "";

    if (!canPreview) {
      return (
        <div className={`flex items-center justify-center h-full ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          <div className="text-center">
            <div className="text-4xl mb-3">📄</div>
            <div className="text-sm">{t.selectFileHint || "选择文件以预览"}</div>
          </div>
        </div>
      );
    }

    if (previewLoading) {
      return (
        <div className={`flex items-center justify-center h-full ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          {t.loading || "加载中..."}
        </div>
      );
    }

    if (previewError) {
      return (
        <div className={`p-4 ${isDark ? "text-rose-300" : "text-rose-600"}`}>
          {previewError}
        </div>
      );
    }

    if (!preview) {
      return (
        <div className={`flex items-center justify-center h-full ${isDark ? "text-slate-500" : "text-slate-400"}`}>
          {t.noPreview || "暂无可预览内容"}
        </div>
      );
    }

    return (
      <div className="flex flex-col h-full">
        {/* 预览头部 */}
        <div className={`flex items-center justify-between px-4 py-2 border-b flex-shrink-0 ${
          isDark ? "border-slate-700 bg-slate-800/50" : "border-slate-200 bg-slate-50"
        }`}>
          <div className="flex items-center gap-2 min-w-0">
            <span>{getFileIcon(fileName)}</span>
            <span className={`text-sm font-medium truncate ${isDark ? "text-slate-200" : "text-slate-700"}`}>
              {fileName}
            </span>
            <span className={`text-xs ${isDark ? "text-slate-500" : "text-slate-400"}`}>
              L{preview.startLine}-{preview.endLine}
              {preview.truncated && ` (${t.truncated || "截断"})`}
            </span>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => revealInExplorer()}
              className={`p-1.5 rounded-lg transition-colors ${
                isDark ? "hover:bg-slate-700 text-slate-400" : "hover:bg-slate-200 text-slate-500"
              }`}
              title={t.reveal || "在资源管理器中显示"}
            >
              <Icons.Folder />
            </button>
            <button
              onClick={() => copyPath()}
              className={`p-1.5 rounded-lg transition-colors ${
                isDark ? "hover:bg-slate-700 text-slate-400" : "hover:bg-slate-200 text-slate-500"
              }`}
              title={copied ? (t.copied || "已复制") : (t.copyPath || "复制路径")}
            >
              <Icons.Copy />
            </button>
            <button
              onClick={() => openInVSCode()}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                isDark
                  ? "bg-slate-700 text-slate-200 hover:bg-slate-600"
                  : "bg-slate-800 text-white hover:bg-slate-700"
              }`}
            >
              {t.openInVSCode || "VS Code"}
            </button>
          </div>
        </div>

        {/* 预览内容 */}
        <div className="flex-1 overflow-auto">
          <div className="min-w-[500px]">
            {previewLines.map((line, idx) => {
              const lineNo = preview.startLine + idx;
              return (
                <button
                  key={lineNo}
                  onClick={() => void openInVSCode(lineNo)}
                  className={`w-full text-left font-mono text-xs px-2 py-0.5 flex hover:underline ${
                    isDark ? "hover:bg-slate-800" : "hover:bg-slate-100"
                  }`}
                  title={`${t.openAtLine || "打开到行"} ${lineNo}`}
                >
                  <span className={`w-12 text-right pr-3 flex-shrink-0 select-none ${
                    isDark ? "text-slate-600" : "text-slate-300"
                  }`}>
                    {lineNo}
                  </span>
                  <span className={`whitespace-pre ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                    {line}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 加载更多 */}
        {preview.truncated && (
          <div className={`px-4 py-2 border-t flex-shrink-0 ${
            isDark ? "border-slate-700" : "border-slate-200"
          }`}>
            <button
              onClick={() => {
                const relFile = selectedRoot?.kind === "file" ? "" : (selectedFileRel ?? "");
                const nextStart = preview.endLine + 1;
                void loadPreview(rootId, relFile, nextStart);
              }}
              className={`text-xs font-medium ${
                isDark ? "text-blue-400 hover:text-blue-300" : "text-blue-600 hover:text-blue-500"
              }`}
            >
              {t.loadMore || "加载更多"} →
            </button>
          </div>
        )}
      </div>
    );
  };

  // ========== 主渲染 ==========
  return (
    <section className={`rounded-2xl border shadow-sm overflow-hidden ${
      isDark ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-slate-200"
    }`}>
      {/* 顶部工具栏 */}
      <div className={`px-4 py-3 border-b flex items-center gap-3 ${
        isDark ? "border-slate-700 bg-slate-800/50" : "border-slate-200 bg-slate-50"
      }`}>
        <h2 className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
          🗂️ {t.artifactsTitle || "产物浏览器"}
        </h2>
        <div className="flex-1" />

        {/* 搜索框 */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
          isDark ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"
        }`}>
          <Icons.Search />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={lang === "zh" ? "搜索文件..." : "Search files..."}
            className={`bg-transparent text-sm outline-none w-40 ${
              isDark ? "text-slate-200 placeholder-slate-500" : "text-slate-700 placeholder-slate-400"
            }`}
          />
        </div>

        {/* 排序下拉 */}
        <select
          value={sortMode}
          onChange={(e) => setSortMode(e.target.value as SortMode)}
          className={`px-3 py-1.5 rounded-lg border text-sm ${
            isDark
              ? "bg-slate-800 border-slate-700 text-slate-200"
              : "bg-white border-slate-200 text-slate-700"
          }`}
        >
          <option value="modified">{lang === "zh" ? "最近修改" : "Recent"}</option>
          <option value="name">{lang === "zh" ? "名称" : "Name"}</option>
          <option value="size">{lang === "zh" ? "大小" : "Size"}</option>
        </select>

        {/* 刷新按钮 */}
        <button
          onClick={() => loadRoots()}
          disabled={rootsLoading}
          className={`p-2 rounded-lg transition-colors ${
            isDark
              ? "hover:bg-slate-700 text-slate-400 disabled:opacity-50"
              : "hover:bg-slate-200 text-slate-500 disabled:opacity-50"
          }`}
          title={t.refresh || "刷新"}
        >
          <Icons.Refresh />
        </button>
      </div>

      {rootsError && (
        <div className={`px-4 py-2 text-sm ${isDark ? "bg-rose-900/30 text-rose-300" : "bg-rose-50 text-rose-600"}`}>
          {rootsError}
        </div>
      )}

      {/* 主体三栏布局 */}
      <div className="flex" style={{ height: "calc(100vh - 280px)", minHeight: "400px" }}>
        {/* 左侧边栏 - 树形导航 */}
        <div className={`w-52 flex-shrink-0 border-r overflow-y-auto p-3 ${
          isDark ? "border-slate-700 bg-slate-900/50" : "border-slate-200 bg-slate-50/50"
        }`}>
          {renderSidebarTree()}
        </div>

        {/* 中间 - 文件列表 */}
        <div className={`w-80 flex-shrink-0 border-r overflow-y-auto ${
          isDark ? "border-slate-700" : "border-slate-200"
        }`}>
          {/* 面包屑 */}
          {selectedRoot?.kind === "dir" && (
            <div className={`px-3 py-2 border-b flex items-center gap-1 text-xs ${
              isDark ? "border-slate-700 bg-slate-800/30" : "border-slate-100 bg-slate-50"
            }`}>
              <button
                onClick={() => void navigateToDir("")}
                className={`px-1.5 py-0.5 rounded hover:underline ${
                  isDark ? "text-slate-400 hover:text-slate-200" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {selectedRoot.relPath}
              </button>
              {breadcrumbParts.map((part, idx) => {
                const next = joinPath(breadcrumbParts.slice(0, idx + 1));
                return (
                  <span key={next} className="flex items-center gap-1">
                    <span className={isDark ? "text-slate-600" : "text-slate-300"}>/</span>
                    <button
                      onClick={() => void navigateToDir(next)}
                      className={`px-1.5 py-0.5 rounded hover:underline ${
                        isDark ? "text-slate-400 hover:text-slate-200" : "text-slate-500 hover:text-slate-700"
                      }`}
                    >
                      {part}
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          {dirError && (
            <div className={`px-3 py-2 text-xs ${isDark ? "text-rose-300" : "text-rose-600"}`}>
              {dirError}
            </div>
          )}

          {renderFileList()}
        </div>

        {/* 右侧 - 预览区 */}
        <div className="flex-1 min-w-0 overflow-hidden">
          {renderPreview()}
        </div>
      </div>
    </section>
  );
}
