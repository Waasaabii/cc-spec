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

export function ProjectArtifactsPanel({ theme, t, projectPath }: ProjectArtifactsPanelProps) {
  const isDark = theme === "dark";

  const [roots, setRoots] = useState<ArtifactRoot[]>([]);
  const [rootsLoading, setRootsLoading] = useState(false);
  const [rootsError, setRootsError] = useState<string | null>(null);

  const [rootId, setRootId] = useState<string>("cc_spec");
  const [dirPath, setDirPath] = useState<string>("");
  const [entries, setEntries] = useState<ArtifactEntry[]>([]);
  const [dirLoading, setDirLoading] = useState(false);
  const [dirError, setDirError] = useState<string | null>(null);

  const [selectedFileRel, setSelectedFileRel] = useState<string | null>(null);
  const [preview, setPreview] = useState<TextPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewStartLine, setPreviewStartLine] = useState<number>(1);
  const [lineInput, setLineInput] = useState<string>("");
  const [copied, setCopied] = useState(false);

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
    setPreviewStartLine(1);
    setLineInput("");

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
    setPreviewStartLine(1);
    setLineInput("");
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
    setPreviewStartLine(1);
    setLineInput("");
    await loadPreview(rootId, relFile, 1);
  }, [loadPreview, rootId]);

  const previewLines = useMemo(() => {
    if (!preview) return [];
    if (!preview.content) return [""];
    return preview.content.split("\n");
  }, [preview]);

  const canPreview = Boolean(selectedRoot && selectedRoot.exists && (selectedRoot.kind === "file" || selectedFileRel));

  const currentPathLabel = useMemo(() => {
    if (!selectedRoot) return "";
    const base = selectedRoot.relPath;
    if (selectedRoot.kind === "file") return base;
    if (!dirPath) return base;
    return `${base}/${dirPath}`;
  }, [dirPath, selectedRoot]);

  const renderEntryRow = (entry: ArtifactEntry) => {
    const icon = entry.kind === "dir" ? <Icons.Folder /> : <Icons.FileText />;
    const meta = entry.kind === "dir"
      ? (t.artifactFolder || "文件夹")
      : `${formatBytes(entry.size)}${entry.modifiedAt ? ` · ${entry.modifiedAt}` : ""}`;

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
        className={`w-full text-left px-3 py-2 rounded-xl border transition-colors ${isDark
          ? "border-slate-800 bg-slate-900/60 hover:bg-slate-800/60"
          : "border-slate-100 bg-white hover:bg-slate-50"
          }`}
      >
        <div className="flex items-start gap-2">
          <div className={`mt-0.5 ${isDark ? "text-slate-400" : "text-slate-500"}`}>{icon}</div>
          <div className="min-w-0 flex-1">
            <div className={`text-sm font-semibold truncate ${isDark ? "text-slate-100" : "text-slate-800"}`}>{entry.name}</div>
            <div className={`text-[10px] font-mono truncate mt-1 ${isDark ? "text-slate-500" : "text-slate-400"}`}>{meta}</div>
          </div>
        </div>
      </button>
    );
  };

  return (
    <section className={`rounded-3xl border shadow-sm p-5 ${isDark ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className={`text-base font-semibold tracking-tight ${isDark ? "text-slate-100" : "text-slate-900"}`}>{t.artifactsTitle || "cc-spec 产物"}</h2>
            <p className={`text-xs mt-1 ${isDark ? "text-slate-400" : "text-slate-500"}`}>{t.artifactsHint || "浏览项目内 cc-spec 生成的文件，默认在 VS Code 中编辑"}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => loadRoots()}
              disabled={rootsLoading}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
            >
              <Icons.Refresh />
              {rootsLoading ? (t.loading || "加载中") : (t.refresh || "刷新")}
            </button>
          </div>
        </div>

        {rootsError && (
          <div className={`text-xs px-3 py-2 rounded-xl border ${isDark ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
            {rootsError}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {roots.map((r) => (
              <button
                key={r.id}
                onClick={() => void selectRoot(r.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors border ${rootId === r.id
                  ? (isDark ? "bg-slate-800 text-slate-100 border-slate-700" : "bg-slate-900 text-white border-slate-900")
                  : (isDark ? "bg-slate-900/60 text-slate-300 border-slate-800 hover:bg-slate-800/60" : "bg-white text-slate-600 border-slate-100 hover:bg-slate-50")
                  }`}
              title={r.absPath}
            >
              <span className="font-mono">{r.label}</span>
              {!r.exists && (
                <span className={`ml-2 text-[10px] px-2 py-0.5 rounded-full ${isDark ? "bg-slate-800 text-slate-400" : "bg-slate-100 text-slate-500"}`}>
                  {t.notGenerated || "未生成"}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.2fr,1.8fr]">
          <div className={`rounded-2xl border p-4 ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.artifactsBrowser || "浏览"}</div>
                <div className={`mt-2 text-[10px] font-mono truncate ${isDark ? "text-slate-400" : "text-slate-500"}`}>{currentPathLabel}</div>
              </div>
              {selectedRoot?.kind === "dir" && (
                <button
                  onClick={() => {
                    const parts = splitPath(dirPath);
                    parts.pop();
                    void navigateToDir(joinPath(parts));
                  }}
                  disabled={!dirPath || dirLoading}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
                >
                  <span aria-hidden>↑</span>
                  {t.up || "上一级"}
                </button>
              )}
            </div>

            {selectedRoot?.kind === "dir" && breadcrumbParts.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1 text-xs">
                <button
                  onClick={() => void navigateToDir("")}
                  className={`px-2 py-1 rounded-lg border ${isDark ? "border-slate-800 bg-slate-900/60 text-slate-300 hover:bg-slate-800/60" : "border-slate-100 bg-white text-slate-600 hover:bg-slate-50"}`}
                >
                  {selectedRoot.relPath}
                </button>
                {breadcrumbParts.map((part, idx) => {
                  const next = joinPath(breadcrumbParts.slice(0, idx + 1));
                  return (
                    <button
                      key={next}
                      onClick={() => void navigateToDir(next)}
                      className={`px-2 py-1 rounded-lg border ${isDark ? "border-slate-800 bg-slate-900/60 text-slate-300 hover:bg-slate-800/60" : "border-slate-100 bg-white text-slate-600 hover:bg-slate-50"}`}
                    >
                      / {part}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="mt-4 flex flex-col gap-2">
              {selectedRoot && !selectedRoot.exists ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.notGeneratedHint || "该项尚未生成或已被清理"}</div>
              ) : selectedRoot?.kind === "file" ? (
                <div className={`text-xs font-mono break-all ${isDark ? "text-slate-300" : "text-slate-700"}`}>{selectedRoot.absPath}</div>
              ) : dirLoading ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.loading || "加载中"}</div>
              ) : entries.length === 0 ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.emptyFolder || "空文件夹"}</div>
              ) : (
                <div className="flex flex-col gap-2">
                  {entries.map(renderEntryRow)}
                </div>
              )}
            </div>

            {dirError && (
              <div className={`mt-4 text-xs px-3 py-2 rounded-xl border ${isDark ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
                {dirError}
              </div>
            )}
          </div>

          <div className={`rounded-2xl border p-4 ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.preview || "预览"}</div>
                  <div className={`mt-2 text-[10px] font-mono truncate ${isDark ? "text-slate-400" : "text-slate-500"}`}>{selectedRoot?.kind === "file" ? selectedRoot.relPath : (selectedFileRel ? `${selectedRoot?.relPath}/${selectedFileRel}` : "")}</div>
                </div>
                <div className="flex flex-wrap gap-2 justify-end">
                  <button
                    onClick={() => revealInExplorer()}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                  >
                    {t.reveal || "在资源管理器中显示"}
                  </button>
                  <button
                    onClick={() => copyPath()}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                    disabled={!currentDirAbsPath && !selectedFileAbsPath}
                  >
                    <Icons.Copy />
                    {copied ? (t.copied || "已复制") : (t.copyPath || "复制路径")}
                  </button>
                  <button
                    onClick={() => openInVSCode()}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-700 text-slate-100 hover:bg-slate-600" : "bg-slate-900 text-white hover:bg-slate-800"}`}
                    disabled={!canPreview}
                  >
                    <Icons.FileText />
                    {t.openInVSCode || "VS Code 打开"}
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>{t.jumpToLine || "跳转到行"}:</div>
                <input
                  value={lineInput}
                  onChange={(e) => setLineInput(e.target.value)}
                  placeholder="1"
                  className={`w-24 px-2 py-1 rounded-lg text-xs font-mono border outline-none ${isDark ? "bg-slate-900/60 border-slate-700 text-slate-200" : "bg-white border-slate-200 text-slate-800"}`}
                />
                <button
                  onClick={() => {
                    const parsed = Number.parseInt(lineInput, 10);
                    if (!Number.isFinite(parsed) || parsed <= 0) return;
                    void openInVSCode(parsed);
                  }}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                  disabled={!canPreview}
                >
                  {t.openAtLine || "打开到行"}
                </button>
                <button
                  onClick={() => {
                    const parsed = Number.parseInt(lineInput || String(previewStartLine), 10);
                    const next = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
                    setPreviewStartLine(next);
                    const relFile = selectedRoot?.kind === "file" ? "" : (selectedFileRel ?? "");
                    if (!selectedRoot || !selectedRoot.exists) return;
                    if (selectedRoot.kind === "dir" && !relFile) return;
                    void loadPreview(rootId, relFile, next);
                  }}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                  disabled={!canPreview}
                >
                  {t.previewFromLine || "从该行预览"}
                </button>
              </div>
            </div>

            <div className="mt-4">
              {!selectedRoot ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.selectArtifactHint || "请选择一个产物目录/文件"}</div>
              ) : !selectedRoot.exists ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.notGeneratedHint || "该项尚未生成或已被清理"}</div>
              ) : selectedRoot.kind === "dir" && !selectedFileRel ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.selectFileHint || "选择一个文件以预览（目录仅用于浏览）"}</div>
              ) : previewLoading ? (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.loading || "加载中"}</div>
              ) : previewError ? (
                <div className={`text-xs px-3 py-2 rounded-xl border whitespace-pre-wrap break-all ${isDark ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
                  {previewError}
                </div>
              ) : preview ? (
                <div className={`rounded-2xl border overflow-hidden ${isDark ? "border-slate-800 bg-slate-950/40" : "border-slate-100 bg-slate-50"}`}>
                  <div className={`px-3 py-2 text-[10px] flex items-center justify-between gap-3 ${isDark ? "border-b border-slate-800 text-slate-400" : "border-b border-slate-100 text-slate-500"}`}>
                    <div className="font-mono">
                      {t.lines || "Lines"}: {preview.startLine} - {preview.endLine}
                      {preview.truncated ? ` · ${t.truncated || "已截断"}` : ""}
                    </div>
                    {preview.truncated && (
                      <button
                        onClick={() => {
                          const relFile = selectedRoot.kind === "file" ? "" : (selectedFileRel ?? "");
                          const nextStart = preview.endLine + 1;
                          setPreviewStartLine(nextStart);
                          void loadPreview(rootId, relFile, nextStart);
                        }}
                        className={`px-2 py-1 rounded-lg border text-[10px] font-semibold ${isDark ? "border-slate-800 bg-slate-900/60 text-slate-300 hover:bg-slate-800/60" : "border-slate-100 bg-white text-slate-600 hover:bg-slate-50"}`}
                      >
                        {t.loadMore || "继续"}
                      </button>
                    )}
                  </div>
                  <div className="max-h-[520px] overflow-auto custom-scrollbar">
                    <div className="min-w-[640px]">
                      {previewLines.map((line, idx) => {
                        const lineNo = preview.startLine + idx;
                        return (
                          <button
                            key={lineNo}
                            onClick={() => void openInVSCode(lineNo)}
                            className={`w-full text-left font-mono text-[11px] px-3 py-1 grid grid-cols-[80px,1fr] gap-3 hover:underline ${isDark ? "text-slate-200 hover:bg-slate-900/60" : "text-slate-800 hover:bg-white"}`}
                            title={(t.openAtLine || "打开到行") + ` ${lineNo}`}
                          >
                            <span className={`text-right ${isDark ? "text-slate-500" : "text-slate-400"}`}>{lineNo}</span>
                            <span className="whitespace-pre">{line}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <div className={`text-sm ${isDark ? "text-slate-500" : "text-slate-400"}`}>{t.noPreview || "暂无可预览内容"}</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
