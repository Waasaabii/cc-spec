import { useEffect, useMemo, useRef, useState } from "react";
import { join } from "@tauri-apps/api/path";
import { open } from "@tauri-apps/plugin-dialog";
import { readTextFile } from "@tauri-apps/plugin-fs";

const MAX_LINES = 400;

type StreamManifest = {
  host: string;
  port: number;
  path: string;
  started_at?: string;
};

type RunStatus = "running" | "completed" | "error";

type RunState = {
  runId: string;
  sessionId?: string | null;
  status: RunStatus;
  startedAt?: string;
  completedAt?: string;
  success?: boolean;
  exitCode?: number;
  errorType?: string;
  duration?: number;
  lines: string[];
};

type ConnectionState = "idle" | "connecting" | "connected" | "error";

const isTauriRuntime = () => {
  if (typeof window === "undefined") {
    return false;
  }
  const w = window as { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown };
  return Boolean(w.__TAURI__ || w.__TAURI_INTERNALS__);
};

const buildManifestPathFallback = (root: string) => {
  const sep = root.includes("\\") ? "\\" : "/";
  const trimmed = root.replace(/[\\/]+$/, "");
  return `${trimmed}${sep}.cc-spec${sep}runtime${sep}codex${sep}stream.json`;
};

const formatDuration = (duration?: number) => {
  if (!duration && duration !== 0) {
    return "-";
  }
  if (duration < 1) {
    return `${Math.round(duration * 1000)}ms`;
  }
  if (duration < 60) {
    return `${duration.toFixed(2)}s`;
  }
  const minutes = Math.floor(duration / 60);
  const seconds = Math.round(duration % 60);
  return `${minutes}m ${seconds}s`;
};

const formatTimestamp = (value?: string) => {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return value;
  }
  return date.toLocaleString();
};

export default function App() {
  const [projectRoot, setProjectRoot] = useState("");
  const [manifestPath, setManifestPath] = useState<string | null>(null);
  const [manifest, setManifest] = useState<StreamManifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);

  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [connectionMessage, setConnectionMessage] = useState<string>(
    "Waiting for manifest."
  );

  const [runs, setRuns] = useState<RunState[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const tauriAvailable = useMemo(() => isTauriRuntime(), []);

  const sseUrl = useMemo(() => {
    if (!manifest) {
      return "";
    }
    return `http://${manifest.host}:${manifest.port}${manifest.path}`;
  }, [manifest]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  const updateRun = (runId: string, updater: (prev: RunState | null) => RunState) => {
    setRuns((prev) => {
      const index = prev.findIndex((run) => run.runId === runId);
      const existing = index >= 0 ? prev[index] : null;
      const next = updater(existing);
      if (index >= 0) {
        const clone = [...prev];
        clone[index] = next;
        return clone;
      }
      return [next, ...prev];
    });
  };

  const loadManifestFromRoot = async (root: string) => {
    setManifestError(null);
    setManifest(null);
    setManifestPath(null);

    if (!root.trim()) {
      setManifestError("请输入项目目录或使用选择按钮。");
      return;
    }

    let targetPath = buildManifestPathFallback(root.trim());
    if (tauriAvailable) {
      try {
        targetPath = await join(root.trim(), ".cc-spec", "runtime", "codex", "stream.json");
      } catch (_error) {
        targetPath = buildManifestPathFallback(root.trim());
      }
    }
    setManifestPath(targetPath);

    try {
      const raw = await readTextFile(targetPath);
      const parsed = JSON.parse(raw) as StreamManifest;
      if (!parsed || typeof parsed.host !== "string" || typeof parsed.port !== "number" || typeof parsed.path !== "string") {
        throw new Error("manifest format invalid");
      }
      setManifest(parsed);
      setConnectionState("idle");
      setConnectionMessage("Manifest loaded. Ready to connect.");
    } catch (error) {
      setManifestError(
        `无法读取 stream.json：${
          error instanceof Error ? error.message : "unknown error"
        }`
      );
      setConnectionState("error");
      setConnectionMessage("Manifest load failed.");
    }
  };

  const handlePickProject = async () => {
    setManifestError(null);
    try {
      const selection = await open({
        title: "选择 cc-spec 项目目录",
        directory: true,
        multiple: false
      });
      if (!selection) {
        return;
      }
      const root = Array.isArray(selection) ? selection[0] : selection;
      setProjectRoot(root);
      await loadManifestFromRoot(root);
    } catch (error) {
      setManifestError(
        `打开目录失败：${error instanceof Error ? error.message : "unknown error"}`
      );
    }
  };

  const disconnect = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConnectionState("idle");
    setConnectionMessage("Disconnected.");
  };

  const connect = () => {
    if (!manifest) {
      setConnectionState("error");
      setConnectionMessage("Manifest missing. Load stream.json first.");
      return;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setConnectionState("connecting");
    setConnectionMessage("Connecting to SSE...");

    const source = new EventSource(sseUrl);
    eventSourceRef.current = source;

    source.onopen = () => {
      setConnectionState("connected");
      setConnectionMessage("Live connection established.");
    };

    source.onerror = () => {
      setConnectionState("error");
      setConnectionMessage("Connection lost. Check the SSE server.");
    };

    const parsePayload = (event: MessageEvent) => {
      try {
        return JSON.parse(event.data);
      } catch (error) {
        return null;
      }
    };

    source.addEventListener("codex.started", (event) => {
      const payload = parsePayload(event as MessageEvent);
      if (!payload || !payload.run_id) {
        return;
      }
      updateRun(payload.run_id, (prev) => ({
        runId: payload.run_id,
        sessionId: payload.session_id ?? prev?.sessionId,
        status: prev?.status ?? "running",
        startedAt: payload.ts ?? prev?.startedAt,
        completedAt: prev?.completedAt,
        success: prev?.success,
        exitCode: prev?.exitCode,
        errorType: prev?.errorType,
        duration: prev?.duration,
        lines: prev?.lines ?? []
      }));
    });

    source.addEventListener("codex.stream", (event) => {
      const payload = parsePayload(event as MessageEvent);
      if (!payload || !payload.run_id) {
        return;
      }
      const text = typeof payload.text === "string" ? payload.text : "";
      if (!text) {
        return;
      }
      updateRun(payload.run_id, (prev) => {
        const base: RunState = prev ?? {
          runId: payload.run_id,
          status: "running",
          lines: []
        };
        if (base.status === "completed") {
          return base;
        }
        const nextLines = [...base.lines, text];
        if (nextLines.length > MAX_LINES) {
          nextLines.splice(0, nextLines.length - MAX_LINES);
        }
        return {
          ...base,
          sessionId: payload.session_id ?? base.sessionId,
          lines: nextLines
        };
      });
    });

    source.addEventListener("codex.error", (event) => {
      const payload = parsePayload(event as MessageEvent);
      if (!payload || !payload.run_id) {
        return;
      }
      updateRun(payload.run_id, (prev) => ({
        runId: payload.run_id,
        sessionId: payload.session_id ?? prev?.sessionId,
        status: "error",
        startedAt: prev?.startedAt,
        completedAt: prev?.completedAt,
        success: prev?.success,
        exitCode: prev?.exitCode,
        errorType: payload.error_type ?? prev?.errorType,
        duration: prev?.duration,
        lines: prev?.lines ?? []
      }));
    });

    source.addEventListener("codex.completed", (event) => {
      const payload = parsePayload(event as MessageEvent);
      if (!payload || !payload.run_id) {
        return;
      }
      updateRun(payload.run_id, (prev) => ({
        runId: payload.run_id,
        sessionId: payload.session_id ?? prev?.sessionId,
        status: "completed",
        startedAt: prev?.startedAt,
        completedAt: payload.ts ?? prev?.completedAt,
        success: payload.success ?? prev?.success,
        exitCode: payload.exit_code ?? prev?.exitCode,
        errorType: payload.error_type ?? prev?.errorType,
        duration: payload.duration_s ?? prev?.duration,
        lines: prev?.lines ?? []
      }));
    });
  };

  const clearRuns = () => {
    setRuns([]);
  };

  const activeCount = runs.filter((run) => run.status === "running").length;
  const completedCount = runs.filter((run) => run.status === "completed").length;

  return (
    <div className="min-h-screen text-[color:var(--ink)]">
      <div className="relative overflow-hidden">
        <div className="absolute -left-32 top-12 h-64 w-64 rounded-full bg-[radial-gradient(circle_at_30%_30%,rgba(255,173,124,0.8),rgba(255,173,124,0)_70%)] blur-2xl" />
        <div className="absolute right-[-80px] top-28 h-72 w-72 rounded-full bg-[radial-gradient(circle_at_70%_20%,rgba(110,196,255,0.7),rgba(110,196,255,0)_70%)] blur-2xl" />
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-6 pb-16 pt-12">
          <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                cc-spec / Codex
              </p>
              <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">
                Codex Stream Viewer
              </h1>
              <p className="max-w-2xl text-sm text-slate-600 md:text-base">
                一键导入项目目录，实时订阅 Codex SSE 输出。多 run_id 并行展示，完成态自动冻结。
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs text-slate-600">
                Active: {activeCount}
              </span>
              <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs text-slate-600">
                Completed: {completedCount}
              </span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  connectionState === "connected"
                    ? "bg-emerald-500/15 text-emerald-700"
                    : connectionState === "connecting"
                    ? "bg-amber-500/15 text-amber-700"
                    : connectionState === "error"
                    ? "bg-rose-500/15 text-rose-700"
                    : "bg-slate-200/80 text-slate-600"
                }`}
              >
                {connectionState.toUpperCase()}
              </span>
            </div>
          </header>

          <section className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-3xl border border-white/60 bg-white/70 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur">
              <h2 className="text-lg font-semibold">Project</h2>
              <p className="mt-2 text-sm text-slate-600">
                选择 cc-spec 项目目录，读取 <span className="font-mono">.cc-spec/runtime/codex/stream.json</span>。
              </p>
              <div className="mt-5 flex flex-col gap-3">
                <input
                  value={projectRoot}
                  onChange={(event) => setProjectRoot(event.target.value)}
                  placeholder="C:\\develop\\cc-spec"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none ring-slate-200 transition focus:ring-2"
                />
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => loadManifestFromRoot(projectRoot)}
                    className="rounded-full bg-[color:var(--ink)] px-4 py-2 text-sm font-semibold text-white transition hover:scale-[1.02]"
                  >
                    Load manifest
                  </button>
                  <button
                    onClick={handlePickProject}
                    disabled={!tauriAvailable}
                    className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Browse folder
                  </button>
                  <button
                    onClick={clearRuns}
                    className="rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-500 hover:text-slate-700"
                  >
                    Clear runs
                  </button>
                </div>
                {!tauriAvailable && (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-700">
                    Tauri API 未检测到。请使用 <span className="font-mono">tauri dev</span> 启动或手动输入路径。
                  </div>
                )}
                {manifestError && (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
                    {manifestError}
                  </div>
                )}
              </div>
              <div className="mt-5 grid gap-2 text-xs text-slate-600">
                <div>
                  <span className="font-semibold text-slate-700">Manifest path:</span> {manifestPath ?? "-"}
                </div>
                <div>
                  <span className="font-semibold text-slate-700">Manifest started:</span> {formatTimestamp(manifest?.started_at)}
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-white/60 bg-white/70 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur">
              <h2 className="text-lg font-semibold">Stream</h2>
              <p className="mt-2 text-sm text-slate-600">单一 SSE 连接，自动分发 run_id。</p>
              <div className="mt-5 space-y-3">
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
                  {sseUrl || "Waiting for manifest..."}
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={connect}
                    className="rounded-full bg-[color:var(--accent)] px-4 py-2 text-sm font-semibold text-white shadow-[0_10px_30px_rgba(255,122,89,0.35)]"
                  >
                    Connect
                  </button>
                  <button
                    onClick={disconnect}
                    className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
                  >
                    Disconnect
                  </button>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
                  {connectionMessage}
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Runs</h2>
              <span className="text-xs text-slate-500">最多保留每个 run 最近 {MAX_LINES} 行</span>
            </div>

            {runs.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-300 bg-white/50 px-6 py-10 text-center text-sm text-slate-500">
                还没有收到任何 Codex 事件。启动 cc-spec Codex 调用并连接 SSE。
              </div>
            ) : (
              <div className="grid gap-4">
                {runs.map((run) => {
                  const statusTone =
                    run.status === "running"
                      ? "bg-emerald-500/15 text-emerald-700"
                      : run.success === false || run.status === "error"
                      ? "bg-rose-500/15 text-rose-700"
                      : "bg-slate-200/80 text-slate-600";

                  return (
                    <div
                      key={run.runId}
                      className="rounded-3xl border border-white/60 bg-white/70 p-5 shadow-[0_15px_40px_rgba(15,23,42,0.08)]"
                    >
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="space-y-1">
                          <div className="text-xs uppercase tracking-[0.25em] text-slate-400">
                            Run
                          </div>
                          <div className="font-mono text-sm text-slate-700">
                            {run.runId}
                          </div>
                          <div className="text-xs text-slate-500">
                            Session: {run.sessionId ?? "-"}
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusTone}`}>
                            {run.status === "running"
                              ? "LIVE"
                              : run.success === false || run.status === "error"
                              ? "FAILED"
                              : "DONE"}
                          </span>
                          <span className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500">
                            Exit {run.exitCode ?? "-"}
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
                        <div>
                          <span className="font-semibold text-slate-700">Started:</span> {formatTimestamp(run.startedAt)}
                        </div>
                        <div>
                          <span className="font-semibold text-slate-700">Completed:</span> {formatTimestamp(run.completedAt)}
                        </div>
                        <div>
                          <span className="font-semibold text-slate-700">Duration:</span> {formatDuration(run.duration)}
                        </div>
                      </div>

                      {run.errorType && (
                        <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                          Error type: {run.errorType}
                        </div>
                      )}

                      <div className="mt-4 max-h-64 overflow-auto rounded-2xl border border-slate-200 bg-slate-950/90 p-3 font-mono text-xs text-slate-100">
                        {run.lines.length === 0 ? (
                          <div className="text-slate-400">暂无输出</div>
                        ) : (
                          run.lines.map((line, idx) => (
                            <div key={`${run.runId}-${idx}`} className="whitespace-pre-wrap">
                              {line}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
