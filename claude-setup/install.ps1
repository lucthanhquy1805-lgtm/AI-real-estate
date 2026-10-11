# Cài cấu hình Claude Code cho dự án (skills, subagents, settings, MCP server).
# Chạy từ gốc repo:   powershell -ExecutionPolicy Bypass -File claude-setup\install.ps1
# Đọc qua các file trong claude-setup\ trước khi chạy: settings.json cấp quyền chạy một số lệnh không cần hỏi.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

New-Item -ItemType Directory -Force -Path ".claude" | Out-Null
Copy-Item -Recurse -Force "claude-setup\claude\*" ".claude\"
Copy-Item -Force "claude-setup\mcp.json" ".mcp.json"

Write-Host "Đã cài:"
Get-ChildItem -Recurse ".claude" -File | ForEach-Object { Write-Host "  " $_.FullName.Substring($root.Length + 1) }
Write-Host "   .mcp.json"
Write-Host ""
Write-Host "Tiếp theo: tạo backend\.venv (xem README), chạy DB, rồi mở Claude Code tại $root và gõ /mcp để kiểm tra server 'aipi'."
