import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Icons } from "../icons/Icons";
import type { translations } from "../../types/viewer";

type CodexSessionRecord = {
  session_id?: string;
  kind?: string;
  mode?: string;
  state?: string;
  pid?: number | null;
  created_at?: string;
  updated_at?: string;
  exit_code?: number | null;
  last_exit_reason?: string | null;
  message?: string | null;
  thread_id?: string | null;
  turn_id?: string | null;
};

type SessionsFile = {
  sessions?: Record<string, CodexSessionRecord>;
};

export function ProjectCodexPanel({
  projectPath,
  isDarkMode,
  t,
}: {
  projectPath: string;
  isDarkMode: boolean;
  t: typeof translations["zh"];
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Record<string, CodexSessionRecord>>({});
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const raw = await invoke<string>("load_sessions", { projectPath });
      const parsed = JSON.parse(raw) as SessionsFile;
      const map = parsed.sessions ?? {};
      setSessions(map);
      if (!selectedSessionId) {
        const ids = Object.keys(map);
        if (ids.length) setSelectedSessionId(ids[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [projectPath, selectedSessionId]);

  useEffect(() => {
    let active = true;
    const run = async () => {
      if (!active) return;
      await load();
    };
    void run();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [load]);

  const terminalSessions = useMemo(() => {
    const entries = Object.entries(sessions).filter(([, rec]) => rec?.kind === "terminal" || rec?.mode === "interactive");
    entries.sort((a, b) => String(b[1]?.updated_at ?? "").localeCompare(String(a[1]?.updated_at ?? "")));
    return entries;
  }, [sessions]);

  const startSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sid = await invoke<string>("codex_terminal_start", { projectPath });
      setSelectedSessionId(sid);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectPath, load]);

  const pauseSession = useCallback(async () => {
    if (!selectedSessionId) return;
    setLoading(true);
    setError(null);
    try {
      await invoke("codex_terminal_pause", { projectPath, sessionId: selectedSessionId, requestedBy: "tool" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectPath, selectedSessionId]);

  const killSession = useCallback(async () => {
    if (!selectedSessionId) return;
    setLoading(true);
    setError(null);
    try {
      await invoke("codex_terminal_kill", { projectPath, sessionId: selectedSessionId, requestedBy: "tool" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectPath, selectedSessionId]);

  const sendPrompt = useCallback(async () => {
    if (!selectedSessionId || !prompt.trim()) return;
    setSending(true);
    setError(null);
    try {
      await invoke<string>("codex_terminal_send_input", {
        projectPath,
        sessionId: selectedSessionId,
        text: prompt,
        requestedBy: "tool",
      });
      setPrompt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }, [projectPath, selectedSessionId, prompt]);

  const copySessionId = useCallback(async (sid: string) => {
    try {
      await navigator.clipboard.writeText(sid);
    } catch (err) {
      console.error("copy failed", err);
    }
  }, []);

  const cardClass = `rounded-3xl border shadow-sm p-5 ${isDarkMode ? "bg-slate-900/70 border-slate-700/60" : "bg-white/80 border-white/70"}`;

  return (
    <section className={cardClass}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className={`text-xs uppercase tracking-[0.2em] font-semibold ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>
            {t.projectTabCodex || "Codex 终端会话"}
          </div>
          <div className={`text-xs mt-1 ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>
            {t.projectCodexHint || "用户在原生终端操作；tool 负责会话/重试/暂停/结果通知"}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => void startSession()}
            disabled={loading}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDarkMode ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
          >
            <Icons.Terminal />
            {t.projectCodexNewSession || "新建会话"}
          </button>
          <button
            onClick={() => void pauseSession()}
            disabled={loading || !selectedSessionId}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDarkMode ? "bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-60" : "bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-60"}`}
          >
            <Icons.Pause />
            {t.pause || "暂停"}
          </button>
          <button
            onClick={() => void killSession()}
            disabled={loading || !selectedSessionId}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDarkMode ? "bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-60" : "bg-rose-500 text-white hover:bg-rose-600 disabled:opacity-60"}`}
          >
            <Icons.Trash />
            {t.stop || "停止"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[320px_1fr]">
        <div className={`rounded-2xl border p-3 ${isDarkMode ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
          <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>
            {t.projectCodexSessions || "会话列表"}
          </div>
          <div className="mt-2 grid gap-2">
            {terminalSessions.length === 0 ? (
              <div className={`text-sm ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>{t.empty || "暂无"}</div>
            ) : (
              terminalSessions.map(([sid, rec]) => {
                const active = sid === selectedSessionId;
                const state = rec.state ?? "-";
                const updated = rec.updated_at ?? rec.created_at ?? "-";
                return (
                  <button
                    key={sid}
                    onClick={() => setSelectedSessionId(sid)}
                    className={`w-full text-left rounded-xl border px-3 py-2 transition-colors ${active
                      ? (isDarkMode ? "border-purple-500/60 bg-purple-500/10" : "border-orange-200 bg-orange-50")
                      : (isDarkMode ? "border-slate-800 bg-slate-900/40 hover:bg-slate-800/60" : "border-slate-100 bg-white hover:bg-slate-50")
                      }`}
                  >
                    <div className={`text-xs font-mono truncate ${isDarkMode ? "text-slate-200" : "text-slate-700"}`}>{sid}</div>
                    <div className={`mt-1 text-[11px] flex flex-wrap gap-2 ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>
                      <span className="font-mono">{state}</span>
                      {typeof rec.pid === "number" ? <span className="font-mono">pid={rec.pid}</span> : null}
                    </div>
                    <div className={`mt-1 text-[10px] font-mono truncate ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>{updated}</div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div className={`rounded-2xl border p-3 ${isDarkMode ? "bg-slate-900/60 border-slate-800" : "bg-white border-slate-100"}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>
                {t.projectCodexSelected || "当前会话"}
              </div>
              <div className={`mt-1 text-xs font-mono break-all ${isDarkMode ? "text-slate-200" : "text-slate-700"}`}>
                {selectedSessionId || "-"}
              </div>
            </div>
            {selectedSessionId ? (
              <button
                onClick={() => void copySessionId(selectedSessionId)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDarkMode ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                title={t.copy || "复制"}
              >
                <Icons.Copy />
                {t.copy || "复制"}
              </button>
            ) : null}
          </div>

          <div className="mt-4">
            <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>
              {t.projectCodexSend || "发送一条提示（注入终端）"}
            </div>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t.projectCodexPromptPlaceholder || "例如：总结这个项目的结构…"}
              rows={4}
              className={`mt-2 w-full rounded-2xl border px-3 py-2 text-sm font-mono outline-none resize-y ${isDarkMode ? "bg-slate-950/60 border-slate-800 text-slate-200 placeholder:text-slate-600" : "bg-white border-slate-200 text-slate-800 placeholder:text-slate-400"}`}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <div className={`text-[11px] ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>
                {t.projectCodexSendHint || "Claude Code 可订阅 codex.managed.turn_complete 拿到最终结果"}
              </div>
              <button
                onClick={() => void sendPrompt()}
                disabled={sending || !selectedSessionId || !prompt.trim()}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${isDarkMode ? "bg-purple-600 text-white hover:bg-purple-500 disabled:opacity-60" : "bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-60"}`}
              >
                <Icons.Send />
                {sending ? (t.loading || "发送中") : (t.send || "发送")}
              </button>
            </div>
          </div>

          {terminalSessions.length > 0 && selectedSessionId && sessions[selectedSessionId] ? (
            <div className={`mt-4 rounded-2xl border p-3 ${isDarkMode ? "border-slate-800 bg-slate-950/40" : "border-slate-100 bg-slate-50"}`}>
              <div className={`text-[10px] uppercase tracking-[0.2em] font-semibold ${isDarkMode ? "text-slate-500" : "text-slate-400"}`}>
                {t.projectCodexLastResult || "最后一次结果"}
              </div>
              <div className={`mt-2 text-sm whitespace-pre-wrap ${isDarkMode ? "text-slate-200" : "text-slate-700"}`}>
                {sessions[selectedSessionId]?.message || "-"}
              </div>
            </div>
          ) : null}

          {error ? (
            <div className={`mt-4 text-xs px-3 py-2 rounded-xl border ${isDarkMode ? "bg-rose-900/30 border-rose-800 text-rose-200" : "bg-rose-50 border-rose-100 text-rose-600"}`}>
              {error}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

