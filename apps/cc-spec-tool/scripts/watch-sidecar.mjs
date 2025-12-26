import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "..");
const SRC_TAURI_DIR = path.join(PROJECT_ROOT, "src-tauri");

const env = {
  ...process.env,
  // 避免与 `tauri dev` 同时跑 cargo 导致 target 目录锁竞争。
  // 产物位置：apps/cc-spec-tool/src-tauri/target-sidecar/{debug,release}/...
  CARGO_TARGET_DIR: process.env.CARGO_TARGET_DIR ?? "target-sidecar",
  // Windows 上偶发出现目标文件被占用（os error 32）；禁用增量编译能显著降低触发概率。
  ...(process.platform === "win32" && !process.env.CARGO_INCREMENTAL
    ? { CARGO_INCREMENTAL: "0" }
    : {}),
};

const sidecarJobs =
  process.env.CC_SPEC_SIDECAR_JOBS ?? (process.platform === "win32" ? "1" : "");
const buildArgs = [
  "build",
  ...(sidecarJobs ? ["-j", sidecarJobs] : []),
  "--bin",
  "cc-spec-codex-relay",
  "--bin",
  "cc-spec-codex-notify",
];

console.log(
  `[watch:sidecar] cwd=${SRC_TAURI_DIR} CARGO_TARGET_DIR=${env.CARGO_TARGET_DIR} CARGO_INCREMENTAL=${env.CARGO_INCREMENTAL ?? "(default)"} jobs=${sidecarJobs || "(default)"}`,
);

const child = spawn(
  "cargo",
  [
    "watch",
    "-w",
    "src/bin",
    "-x",
    buildArgs.join(" "),
  ],
  { cwd: SRC_TAURI_DIR, env, stdio: "inherit", shell: false },
);

child.on("exit", (code, signal) => {
  if (typeof code === "number") {
    process.exit(code);
  }
  if (signal) {
    console.error(`[watch:sidecar] exited by signal: ${signal}`);
  }
  process.exit(1);
});
