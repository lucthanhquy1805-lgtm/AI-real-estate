# Quy trình làm việc với Claude Code

## A. Chuẩn bị — chỉ làm một lần trên mỗi máy

PowerShell, tại `C:\AI\AI-bat-dong-san`:

```powershell
# 1. Python 3.12+ và môi trường ảo (MCP server cần đúng đường dẫn backend\.venv)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
cd ..

# 2. Database (cần Docker Desktop đang chạy)
copy .env.example .env
docker compose up -d db
cd backend
alembic upgrade head
python -m app.db.seed
docker compose exec db psql -U aipi -c "create database aipi_test"
pytest -q                       # phải xanh
cd ..
```

3. Mở Claude Code tại thư mục dự án: `cd C:\AI\AI-bat-dong-san`, rồi `claude`.
4. Gõ `/mcp` và kiểm tra server **aipi** ở trạng thái connected. Nếu được hỏi có tin cậy server từ `.mcp.json` không, chọn đồng ý.
5. Hỏi thử: *"Tóm tắt dự án và nguyên tắc bất biến trong CLAUDE.md"*. Nếu trả lời đúng (Quận 9 cũ, facts-only, không vượt chặn…) thì Claude Code đã hiểu dự án.

## B. Mỗi phiên làm việc

| Bước | Bạn nói với Claude Code | Kiểm tra |
|---|---|---|
| 1. Mở đầu | "Gọi roadmap_next và cho tôi biết việc tiếp theo, DoD và file sẽ sửa." | Việc đúng thứ tự trong ROADMAP |
| 2. Lên kế hoạch | "Lập kế hoạch cho T0.x, chưa sửa code." | Kế hoạch khớp DoD; hỏi lại nếu thiếu |
| 3. Làm | "Làm theo kế hoạch, kèm test." (hoặc "làm bước tiếp theo" để dùng skill next-task) | Claude chạy pytest và ruff |
| 4. Rà soát | "Gọi subagent compliance-reviewer rà diff." | Không có BLOCKER/MAJOR |
| 5. Đóng việc | "Đánh dấu xong trong ROADMAP, ghi RESEARCH_LOG, rồi commit." | `git log` có commit mới |
| 6. Kết thúc | `/clear` trước khi sang việc khác | — |

Quy tắc:
- **Mỗi phiên một việc** (một mã T trong ROADMAP). Việc lớn như T0.5 thì chia nhỏ: "chỉ làm rate limiter và robots checker trước".
- Đọc diff trước khi đồng ý commit.
- Không bao giờ cho phép bỏ qua test, nới lỏng field policy, hay "tạm thời" vượt chặn. Nếu Claude đề xuất, từ chối và nhắc nó đọc CLAUDE.md.
- Gặp lỗi: dán nguyên văn lỗi cho Claude Code, đừng tóm tắt.
- Phiên dài: dùng `/compact` khi hội thoại quá dài.

## C. Vì sao lần sau Claude Code vẫn "nhớ"

Claude Code không nhớ giữa các phiên. Dự án lưu "trí nhớ" bằng file trong repo:

| File | Claude Code dùng để |
|---|---|
| `CLAUDE.md` | Tự đọc mỗi phiên: mục tiêu, nguyên tắc, kiến trúc, lệnh |
| `docs/ROADMAP.md` | Biết việc nào xong, việc nào tiếp theo |
| `docs/RESEARCH_LOG.md` | Biết đã quyết định gì, kết quả ra sao |
| `docs/DATA_DICTIONARY.md` | Biết schema hiện tại và dự kiến |
| `.claude/skills`, `.claude/agents`, `.mcp.json` | Quy trình chuẩn, subagent, công cụ |

Vì vậy, cuối mỗi việc **luôn** yêu cầu cập nhật ROADMAP và RESEARCH_LOG. Khi thay đổi một quyết định lớn (thêm nguồn, đổi khu vực, đổi stack), nói: *"Cập nhật CLAUDE.md và ROADMAP theo quyết định này: …"*.

## D. Kế hoạch gần (theo ROADMAP)

| Thứ tự | Việc | Ước lượng |
|---|---|---|
| 1 | T0.4 — Migration 0002: bảng ingestion và tin đăng (skill db-migration) | 1 buổi |
| 2 | T0.5a — RateLimiter + RobotsChecker | 1 buổi |
| 3 | T0.5b — BlockDetector + TransientStore + HttpClient | 1 buổi |
| 4 | T0.6 — Adapter interface + CLI `ingestion.run --dry-run` | 1 buổi |
| 5 | T0.7 — Pseudonym HMAC | ½ buổi |
| 6 | T1.1 — Connector Batdongsan (skill build-connector) | 2–3 buổi |

Câu mở đầu mẫu cho hôm nay:

> Đọc CLAUDE.md và docs/ROADMAP.md. Làm T0.4 theo skill db-migration: tạo migration 0002 theo docs/DATA_DICTIONARY.md mục 2. Lập kế hoạch trước, chờ tôi đồng ý rồi mới sửa code.

## E. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `password authentication failed for user "aipi"` | Đang kết nối nhầm vào PostgreSQL khác (thường là bản cài sẵn trên Windows ở cổng 5432) | DB của dự án chạy ở **cổng 5433**. Kiểm tra `.env` có `POSTGRES_PORT=5433` và `DATABASE_URL=...localhost:5433/aipi` |
| `service "db" is not running` | Chưa chạy, hoặc chạy lỗi do trùng cổng | Chạy `docker compose up -d db` **ở thư mục gốc**, rồi `docker compose ps`. Nếu lỗi: `docker compose logs db` |
| `port is already allocated` / `Only one usage of each socket address` | Cổng 5433 cũng bị chiếm | Đổi `POSTGRES_PORT` và cổng trong `DATABASE_URL` trong `.env` sang số khác (vd 5434) |
| Docker báo không kết nối được engine | Docker Desktop chưa mở | Mở Docker Desktop, chờ trạng thái "Engine running" |

Kiểm tra cổng nào đang bị dùng (PowerShell): `netstat -ano | findstr :5432`
