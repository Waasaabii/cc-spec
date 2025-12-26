import { request } from "node:http";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HOST = process.env.VITE_HOST ?? "127.0.0.1";
const PORT = Number.parseInt(process.env.VITE_PORT ?? "5173", 10);

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "..");
const VITE_BIN = path.join(PROJECT_ROOT, "node_modules", "vite", "bin", "vite.js");

const MARKERS = [
  "<title>cc-spec tools</title>",
  "/src/main.tsx",
  "logo.gif",
];

function httpGet(path, timeoutMs = 500) {
  return new Promise((resolve, reject) => {
    const req = request(
      {
        host: HOST,
        port: PORT,
        path,
        method: "GET",
        timeout: timeoutMs,
        headers: {
          Accept: "text/html,application/javascript,*/*",
          Connection: "close",
        },
      },
      (res) => {
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          body += chunk;
          if (body.length > 200_000) {
            res.destroy(new Error("response_too_large"));
          }
        });
        res.on("end", () => {
          resolve({ statusCode: res.statusCode ?? 0, body });
        });
      },
    );
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    req.end();
  });
}

async function looksLikeVite() {
  try {
    const res = await httpGet("/@vite/client");
    return res.statusCode === 200;
  } catch {
    return false;
  }
}

async function looksLikeThisApp() {
  try {
    const res = await httpGet("/");
    if (res.statusCode !== 200) {
      return false;
    }
    return MARKERS.every((m) => res.body.includes(m));
  } catch {
    return false;
  }
}

async function portResponds() {
  try {
    const res = await httpGet("/");
    return res.statusCode !== 0;
  } catch {
    return false;
  }
}

async function runViteInProcess() {
  // 让 Vite 在当前 node 进程内启动：避免嵌套 npm（以及 Windows 下 spawn .cmd 的 EINVAL 问题）。
  process.chdir(PROJECT_ROOT);

  // 模拟 `vite` CLI 的 argv，确保行为一致。
  const originalArgv = process.argv;
  process.argv = [
    originalArgv[0],
    VITE_BIN,
    "--host",
    HOST,
    "--port",
    String(PORT),
    "--strictPort",
  ];

  await import(pathToFileURL(VITE_BIN).href);
}

async function main() {
  const url = `http://${HOST}:${PORT}`;

  if (await looksLikeVite()) {
    if (!(await looksLikeThisApp())) {
      console.error(
        `[dev:frontend] Port ${PORT} is already in use by another Vite server (not cc-spec tools).`,
      );
      console.error(`[dev:frontend] Stop that dev server or free ${url} before running Tauri.`);
      process.exit(1);
    }
    console.log(`[dev:frontend] Vite already running at ${url}; skipping start.`);
    return;
  }

  if (await portResponds()) {
    console.error(`[dev:frontend] Port ${PORT} is already in use and does not look like Vite.`);
    console.error(`[dev:frontend] Please stop the process using ${url} and try again.`);
    process.exit(1);
  }

  console.log(`[dev:frontend] Starting Vite at ${url}...`);
  await runViteInProcess();
}

main().catch((err) => {
  console.error("[dev:frontend] Unexpected error:", err);
  process.exit(1);
});
