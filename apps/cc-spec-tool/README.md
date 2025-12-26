# cc-spec-tool

Tauri + Vite 的桌面端 Viewer。

## 开发（推荐）

```bash
cd apps/cc-spec-tool

# 启动 Tauri + 监听 rust sidecar（relay/notifier）
bun run dev:full
```

`dev:full` 会同时跑两件事（终端里会看到两路日志）：

1. `tauri dev`（会通过 `beforeDevCommand` 自动启动 Vite）
2. `watch:sidecar`（监听并构建 `cc-spec-codex-relay` / `cc-spec-codex-notify`）

为避免 `cargo watch` 与 `tauri dev` 同时编译导致 `target` 目录锁竞争，`watch:sidecar` 默认使用独立目录：

- `apps/cc-spec-tool/src-tauri/target-sidecar/`

Tauri 后端在 dev 模式下会优先从该目录查找 sidecar。

Windows 下如果遇到 `os error 32`（文件被占用），`watch:sidecar` 默认会使用 `CARGO_INCREMENTAL=0` 且 `-j 1` 降低概率；如需提速可手动设置：

```powershell
$env:CC_SPEC_SIDECAR_JOBS = "8"
```

## 打包（自动构建前端 + CLI + sidecar，并复制到 src-tauri/sidecar）

```bash
cd apps/cc-spec-tool

# 触发 tauri build（会自动执行 beforeBuildCommand: npm run build:tauri）
bun run tauri build
```

`build:tauri` 会做三件事：

1. 构建前端：`npm run build`（产物在 `apps/cc-spec-tool/dist/`）
2. 构建 Rust sidecar：`cc-spec-codex-relay` / `cc-spec-codex-notify`（release）
3. 打包 cc-spec CLI（PyInstaller）：并把可执行文件复制到 `apps/cc-spec-tool/src-tauri/sidecar/`

复制目标文件示例（Windows x64）：

- `apps/cc-spec-tool/src-tauri/sidecar/cc-spec-x86_64-pc-windows-msvc.exe`
- `apps/cc-spec-tool/src-tauri/sidecar/cc-spec-codex-relay-x86_64-pc-windows-msvc.exe`
- `apps/cc-spec-tool/src-tauri/sidecar/cc-spec-codex-notify-x86_64-pc-windows-msvc.exe`

## 只打包 CLI（手动命令）

推荐：

```bash
cd apps/cc-spec-tool
bun run build:cli
```

或在仓库根目录执行：

```bash
uv run pyinstaller --clean apps/cc-spec-tool/sidecar/cc-spec.spec
```

Windows 下也可以用脚本：

```powershell
pwsh apps/cc-spec-tool/scripts/build-sidecar.ps1
```

## 常见问题

- **`vite` 报 “5173 已被占用”**：`dev:full` 会复用已启动的本项目 Vite；如果 5173 被其它项目占用，需要先释放端口或改端口。
- **Windows `LNK1104`**：通常是某个 `cc-spec-codex-relay.exe` 仍在运行导致输出文件被锁；先结束对应进程再构建。
