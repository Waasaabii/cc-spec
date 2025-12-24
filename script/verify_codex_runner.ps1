param(
  [string]$ProjectPath = (Get-Location).Path,
  [int]$ViewerPort = 38888
)

Write-Host "Codex runner verification checklist"
Write-Host "------------------------------------"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
  Write-Warning "codex CLI not found in PATH. Install it or set CODEX_PATH before running checks."
}

Write-Host "1) Start Viewer (tauri dev) and confirm SSE connected: http://127.0.0.1:$ViewerPort/events"
Write-Host "2) Execute a run: codex exec --skip-git-repo-check --cd `"$ProjectPath`" --json -"
Write-Host "   - Provide a short prompt and verify codex.started/stream/completed in Viewer"
Write-Host "3) Pause current run via Tauri invoke: codex_pause (session_id + optional run_id)"
Write-Host "   - Verify sessions.json state changes to idle"
Write-Host "4) Resume via Tauri invoke: codex_resume (session_id + prompt)"
Write-Host "   - Verify session_id unchanged and new codex.started/stream/completed"
Write-Host "5) Retry behavior: set CODEX_PATH to an invalid path and run codex_resume"
Write-Host "   - Verify 5 attempts and structured hint in stderr"
Write-Host "6) Rollback check: set CC_SPEC_CODEX_RUNNER=python and run CLI path"
Write-Host "   - Verify Python runner still works"
