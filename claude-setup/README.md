# Cấu hình Claude Code cho dự án

Thư mục này chứa bản gốc của:

| File | Cài vào |
|---|---|
| `claude/skills/*` | `.claude/skills/` — 6 skill |
| `claude/agents/*` | `.claude/agents/` — 4 subagent |
| `claude/settings.json` | `.claude/settings.json` — quyền chạy lệnh test/lint/alembic và tool MCP chỉ-đọc không cần hỏi; bật server `aipi` |
| `mcp.json` | `.mcp.json` — khai báo MCP server `aipi` |

Cài đặt (chạy một lần, và chạy lại khi các file ở đây được cập nhật):

```powershell
cd C:\AI\AI-bat-dong-san
powershell -ExecutionPolicy Bypass -File claude-setup\install.ps1
```

Lý do phải tự cài: các file `.claude/` và `.mcp.json` cấp quyền cho Claude Code, nên không được ghi từ xa. Bạn nên xem qua trước khi cài.
