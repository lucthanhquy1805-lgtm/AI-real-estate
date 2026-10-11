# AI Property Intelligence Vietnam

Dự án nghiên cứu cá nhân, phi thương mại: thu thập dữ kiện nhà phố từ nhiều nguồn web để học **định giá** và **đánh giá độ uy tín tin đăng**.
Khu vực khởi đầu là **Quận 9 cũ, TP.HCM**, nay là 5 phường: Tăng Nhơn Phú, Long Bình, Long Phước, Long Trường, Phước Long.

Đặc tả đầy đủ: [`docs/SRS_v1.4.docx`](docs/SRS_v1.4.docx).

## Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| Sprint 0, ngày 1–3: dữ liệu tham chiếu phường, source registry, field policy, khung repo | ✅ |
| Bộ công cụ Claude Code: CLAUDE.md, ROADMAP, skills, subagents, MCP server | ✅ |
| Ngày 4–5: bảng tin đăng, rate limiter, robots checker, block detection | ⏭ tiếp theo |
| Connector Batdongsan (W5), Nhà Tốt (W6) | ⏳ |

## Cấu trúc

```
backend/                      Python: FastAPI + ingestion + (sau này) ML
  app/                        API, cấu hình, DB models, seed
  ingestion/core/policy.py    Field-level policy (không lưu mô tả/ảnh/SĐT)
  ingestion/normalize/        Chuẩn hóa địa chỉ Quận 9 cũ ↔ phường mới
  alembic/                    Migration DB
  tests/                      Unit, compliance, DB tests
packages/contracts/
  sources.yaml                Danh mục nguồn: tầng, quyền, allow_training, rate limit
  field_policy.yaml           Trường nào được lưu / hiển thị
data/reference/               Bảng ánh xạ 13 phường cũ → 5 phường mới (NQ 1685/NQ-UBTVQH15)
infra/docker/                 Dockerfile cho PostgreSQL (PostGIS + pgvector) và backend
apps/web/                     Giao diện Next.js (W11/W16)
docs/                         SRS, chính sách nguồn, nhật ký nghiên cứu
```

## Chạy bằng Docker (khuyến nghị trên Windows)

Yêu cầu: Docker Desktop (bật WSL 2).

```powershell
cd C:\AI\AI-bat-dong-san
copy .env.example .env
docker compose up --build
```

Sau khi chạy:

- API docs: http://localhost:8000/docs
- Kiểm tra: http://localhost:8000/health trả về `postgis`, `vector`, `pg_trgm`
- Danh sách phường: http://localhost:8000/reference/wards
- Thử chuẩn hóa địa chỉ: http://localhost:8000/reference/resolve-ward?address=P.%20Hiệp%20Phú,%20Q.9
- Trạng thái nguồn và policy gate: http://localhost:8000/admin/sources

Container `api` tự chạy migration và seed dữ liệu tham chiếu khi khởi động.

## Chạy backend trực tiếp (để phát triển)

Yêu cầu: Python 3.12+, Postgres chạy qua `docker compose up db`.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
$env:DATABASE_URL="postgresql+psycopg://aipi:aipi@localhost:5432/aipi"
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload
```

## Test

```powershell
cd backend
pytest -q                                  # unit + compliance (không cần DB)
$env:TEST_DATABASE_URL="postgresql+psycopg://aipi:aipi@localhost:5432/aipi_test"
pytest -q                                  # thêm test migration, seed, API
ruff check . ; ruff format --check .
```

Test DB sẽ xóa và tạo lại schema, nên `TEST_DATABASE_URL` phải trỏ tới **database riêng** (ví dụ `aipi_test`):

```powershell
docker compose exec db psql -U aipi -c "create database aipi_test"
```

## Làm việc với Claude Code

Repo đã có sẵn ngữ cảnh để Claude Code làm tiếp:

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| Hướng dẫn chính | `CLAUDE.md` | Mục tiêu, nguyên tắc bất biến, kiến trúc, lệnh, quy ước |
| Kế hoạch | `docs/ROADMAP.md` | Danh sách việc kèm DoD và Files, đánh dấu `[x]` khi xong |
| MCP server | `.mcp.json` (cài từ `claude-setup/`) → `backend/run_mcp.py` | Tool chỉ-đọc: `roadmap_next`, `resolve_ward`, `list_sources`, `check_fields`, `check_robots`, `db_schema`, `db_query`, `data_summary` |
| Skills | `.claude/skills/` (cài từ `claude-setup/`) | `next-task`, `add-source`, `build-connector`, `db-migration`, `model-experiment`, `weekly-report` |
| Subagents | `.claude/agents/` (cài từ `claude-setup/`) | `compliance-reviewer`, `connector-engineer`, `data-quality-analyst`, `ml-researcher` |

Chuẩn bị một lần:

0. Cài cấu hình Claude Code. Các file `.claude/` và `.mcp.json` nằm sẵn trong `claude-setup/`; xem qua rồi chạy:
   `powershell -ExecutionPolicy Bypass -File claude-setup\install.ps1`
1. Tạo venv và cài đặt như mục "Chạy backend trực tiếp". MCP server dùng `backend/.venv/Scripts/python.exe`.
2. `docker compose up -d db`, rồi `alembic upgrade head` và `python -m app.db.seed`. Bước này để các tool DB của MCP có dữ liệu.
3. Mở Claude Code tại thư mục dự án (ví dụ `C:\AI\AI-bat-dong-san`) và chấp nhận MCP server `aipi` khi được hỏi. Gõ `/mcp` để kiểm tra.

Rồi chỉ cần nói: **"làm bước tiếp theo"**. Claude Code sẽ dùng skill `next-task` để lấy việc từ ROADMAP, làm, chạy test, nhờ `compliance-reviewer` rà soát, và đánh dấu xong.

## Nguyên tắc dữ liệu (không được phá vỡ)

1. Mọi nguồn phải có trong `sources.yaml` trước khi crawl. Nguồn chỉ chạy khi `permission_level` cho phép, `status: active` và chưa quá hạn rà soát.
2. Tuân thủ robots.txt, mỗi domain ≥ 6 giây/request, 1 kết nối. Gặp chặn hoặc CAPTCHA thì **dừng**, không vượt.
3. Không lưu mô tả nguyên văn, ảnh, số điện thoại. `field_policy.yaml` và test tuân thủ thực thi điều này.
4. Nguồn có `allow_training: false` (ví dụ Nhà Tốt) không được đưa vào tập huấn luyện.
5. Không chia sẻ dữ liệu thu thập ra ngoài.
