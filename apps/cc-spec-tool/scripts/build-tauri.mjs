import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const viewerRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(viewerRoot, "..", "..");
const srcTauriDir = path.join(viewerRoot, "src-tauri");
const tauriSidecarDir = path.join(srcTauriDir, "sidecar");
const cliSpecPath = path.join(viewerRoot, "sidecar", "cc-spec.spec");

const argv = new Set(process.argv.slice(2));
const dryRun = argv.has("--dry-run");
const skipFrontend = argv.has("--no-frontend");
const skipSidecars = argv.has("--no-sidecars");
const skipCli = argv.has("--no-cli");

function commandName(base) {
  if (process.platform !== "win32") {
    return base;
  }
  // 对于 bun，Windows 下使用 bun.exe
  if (base === "bun") {
    return "bun.exe";
  }
  return base;
}

function run(command, args, options = {}) {
  const cwd = options.cwd ?? process.cwd();
  const allowFailure = options.allowFailure ?? false;
  const stdio = options.stdio ?? "inherit";

  const pretty = [command, ...args].join(" ");
  if (dryRun) {
    console.log(`[dry-run] (${cwd}) ${pretty}`);
    return { status: 0 };
  }

  const result = spawnSync(commandName(command), args, {
    cwd,
    stdio,
    shell: false,
    env: process.env,
  });

  if (result.error) {
    if (allowFailure) {
      return { status: 1 };
    }
    throw result.error;
  }
  if (typeof result.status === "number" && result.status !== 0) {
    if (allowFailure) {
      return { status: result.status };
    }
    throw new Error(`command failed (${result.status}): ${pretty}`);
  }
  return { status: 0 };
}

function ensureDir(dir) {
  if (dryRun) {
    console.log(`[dry-run] mkdir -p ${dir}`);
    return;
  }
  fs.mkdirSync(dir, { recursive: true });
}

function copyFile(src, dest) {
  ensureDir(path.dirname(dest));
  if (dryRun) {
    console.log(`[dry-run] copy ${src} -> ${dest}`);
    return;
  }
  if (!fs.existsSync(src)) {
    throw new Error(`file not found: ${src}`);
  }
  fs.copyFileSync(src, dest);
}

function platformTriple() {
  const arch = process.arch;
  const platform = process.platform;

  if (platform === "win32") {
    if (arch === "x64") return "x86_64-pc-windows-msvc";
    if (arch === "arm64") return "aarch64-pc-windows-msvc";
    if (arch === "ia32") return "i686-pc-windows-msvc";
    throw new Error(`unsupported windows arch: ${arch}`);
  }

  if (platform === "darwin") {
    if (arch === "arm64") return "aarch64-apple-darwin";
    if (arch === "x64") return "x86_64-apple-darwin";
    throw new Error(`unsupported mac arch: ${arch}`);
  }

  if (platform === "linux") {
    if (arch === "x64") return "x86_64-unknown-linux-gnu";
    if (arch === "arm64") return "aarch64-unknown-linux-gnu";
    throw new Error(`unsupported linux arch: ${arch}`);
  }

  throw new Error(`unsupported platform: ${platform}`);
}

function exeExt() {
  return process.platform === "win32" ? ".exe" : "";
}

function resolvePyInstallerOutput() {
  const ext = exeExt();
  const direct = path.join(repoRoot, "dist", `cc-spec${ext}`);
  if (dryRun) {
    return direct;
  }
  if (fs.existsSync(direct)) {
    return direct;
  }
  const oneDir = path.join(repoRoot, "dist", "cc-spec", `cc-spec${ext}`);
  if (fs.existsSync(oneDir)) {
    return oneDir;
  }
  throw new Error(
    `PyInstaller output not found. Tried: ${direct} and ${oneDir}.`,
  );
}

function buildFrontend() {
  run("bun", ["run", "build"], { cwd: viewerRoot });
}

function buildRustSidecars() {
  const manifest = path.join(srcTauriDir, "Cargo.toml");
  run(
    "cargo",
    [
      "build",
      "--manifest-path",
      manifest,
      "--release",
      "--no-default-features",
      "--bin",
      "cc-spec-codex-relay",
      "--bin",
      "cc-spec-codex-notify",
    ],
    { cwd: viewerRoot },
  );

  const triple = platformTriple();
  const ext = exeExt();
  const srcDir = path.join(srcTauriDir, "target", "release");

  for (const name of ["cc-spec-codex-relay", "cc-spec-codex-notify"]) {
    const src = path.join(srcDir, `${name}${ext}`);
    const dest = path.join(tauriSidecarDir, `${name}-${triple}${ext}`);
    copyFile(src, dest);
  }
}

function ensurePyInstallerInstalled() {
  const check = run("uv", ["run", "python", "-c", "import PyInstaller"], {
    cwd: repoRoot,
    allowFailure: true,
    stdio: "ignore",
  });
  if (check.status === 0) {
    return;
  }
  run("uv", ["pip", "install", "pyinstaller"], { cwd: repoRoot });
}

function buildCliSidecar() {
  ensurePyInstallerInstalled();
  run("uv", ["run", "pyinstaller", "--clean", cliSpecPath], { cwd: repoRoot });

  const triple = platformTriple();
  const ext = exeExt();
  const built = resolvePyInstallerOutput();
  const dest = path.join(tauriSidecarDir, `cc-spec-${triple}${ext}`);
  copyFile(built, dest);
}

function main() {
  console.log("[build:tauri] repoRoot:", repoRoot);
  console.log("[build:tauri] viewerRoot:", viewerRoot);
  console.log("[build:tauri] srcTauriDir:", srcTauriDir);
  console.log("[build:tauri] sidecarDir:", tauriSidecarDir);
  ensureDir(tauriSidecarDir);

  if (!skipFrontend) {
    console.log("[build:tauri] Building frontend...");
    buildFrontend();
  }

  if (!skipSidecars) {
    console.log("[build:tauri] Building rust sidecars (relay/notify)...");
    buildRustSidecars();
  }

  if (!skipCli) {
    console.log("[build:tauri] Building cc-spec CLI sidecar (PyInstaller)...");
    buildCliSidecar();
  }

  console.log("[build:tauri] Done.");
}

try {
  main();
} catch (err) {
  console.error("[build:tauri] Failed:", err?.message ?? err);
  if (process.platform === "win32") {
    console.error(
      "[build:tauri] Tip: If you see LNK1104, stop any running cc-spec-codex-relay.exe that is locking the output binary.",
    );
  }
  process.exit(1);
}
