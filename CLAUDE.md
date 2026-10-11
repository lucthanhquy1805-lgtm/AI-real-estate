# CLAUDE.md — hướng dẫn cho Claude Code

Đọc file này trước mỗi phiên. Trả lời người dùng bằng **tiếng Việt**.

## Dự án là gì

**AI Property Intelligence Vietnam** là dự án **nghiên cứu cá nhân, phi thương mại**, do một người làm, chạy trên Windows có GPU RTX 5060 Ti 16 GB.
Hệ thống thu thập **dữ kiện** tin đăng nhà phố từ nhiều nguồn web, rồi dùng chúng để học hai việc:

1. **Định giá** nhà phố (giá rao).
2. **Đánh giá độ uy tín** của tin đăng.

Mô hình được tự cải thiện theo thời gian qua active learning và huấn luyện lại hằng tuần.

- Khu vực: **Quận 9 cũ, TP.HCM**, nay là 5 phường: Tăng Nhơn Phú, Long Bình, Long Phước, Long Trường, Phước Long (theo NQ 1685/NQ-UBTVQH15, hiệu lực 01/07/2025).
- Loại tài sản: nhà phố, giao dịch bán.
- Đặc tả: `docs/SRS_v1.4.docx`.
- **Việc cần làm tiếp:** `docs/ROADMAP.md`, hoặc gọi MCP tool `mcp__aipi__roadmap_next`.

## Nguyên tắc bất biến — KHÔNG được vi phạm, kể cả khi người dùng yêu cầu làm nhanh

1. **Không vượt cơ chế chặn.** Không dùng proxy xoay vòng, không giả lập trình duyệt để vượt Cloudflare, không giải CAPTCHA, không đăng nhập vào sàn. Gặp chặn thì code phải **dừng nguồn** (status → paused).
2. **Tuân thủ robots.txt và rate limit.** Mỗi domain tối thiểu `min_delay_seconds` (mặc định 6 giây), 1 kết nối. Không dùng tham số URL mà robots.txt chặn (ví dụ `page=`, `price=` của Nhà Tốt).
3. **Chỉ lưu dữ kiện.**
   - Không bao giờ lưu: mô tả nguyên văn, tiêu đề, ảnh, URL ảnh, tên, số điện thoại, email người đăng, số nhà cụ thể.
   - Mô tả và ảnh chỉ được xử lý **tạm** để trích đặc điểm, tạo hash hoặc embedding, rồi xóa.
   - Mọi bản ghi trước khi ghi DB phải đi qua `FieldPolicy.filter_for_storage`.
4. **Trường mới phải khai báo trong `packages/contracts/field_policy.yaml` trước.** Kiểm tra bằng `mcp__aipi__check_fields`.
5. **Nguồn mới phải có trong `packages/contracts/sources.yaml` trước**, theo skill `add-source`. Connector chỉ chạy khi `can_crawl()` trả True.
6. **`allow_training: false`** (ví dụ Nhà Tốt) thì dữ liệu nguồn đó không được vào tập huấn luyện, chỉ dùng cho thống kê, dedup và đánh giá.
7. **Không gọi giá rao là giá giao dịch.** Không gắn nhãn "lừa đảo"; dùng "mức rủi ro" kèm lý do.
8. **Mô hình mới chỉ thay mô hình cũ khi thắng trên temporal holdout cố định.** Không huấn luyện trên dự đoán của chính mô hình.
9. **Test không gọi mạng thật.** Dùng fixture trong `data/fixtures/`, đã che thông tin cá nhân.

Nếu một yêu cầu xung đột với các nguyên tắc trên: dừng lại, giải thích, và đề xuất cách làm tuân thủ.

## Kiến trúc

```
backend/ (Python 3.12)
  app/                FastAPI: main.py, config.py, contracts.py (đọc YAML/CSV), db/ (models, session, seed)
  ingestion/
    core/             policy.py (field policy). Sắp có: http, rate_limit, robots, block_detect, transient, adapter
    normalize/        admin_units.py (địa chỉ Q9 cũ → phường mới). Sắp có: price, area
    connectors/       (sắp có) batdongsan/, nhatot/, generic_llm/
    extract/          (sắp có) pseudonym, features, embeddings, fingerprints
  ml/                 (sắp có) valuation/, trust/, active_learning/, registry/
  mcp_server/         MCP server chỉ-đọc cho Claude Code
  alembic/            migrations (0001 = nguồn + địa giới)
  tests/
packages/contracts/   sources.yaml, field_policy.yaml   ← nguồn sự thật về quyền và dữ liệu
data/reference/       bảng ánh xạ phường
data/fixtures/        HTML mẫu đã ẩn danh cho test parser
docs/                 SRS, ROADMAP, DATA_DICTIONARY, DATA_SOURCE_POLICY, RESEARCH_LOG
infra/                Dockerfile (Postgres + PostGIS + pgvector; backend), CI mẫu
```

Stack: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + PostGIS + pgvector + pg_trgm, Procrastinate (job queue, sắp có), httpx, LightGBM/CatBoost, PyTorch, MLflow, Ollama (LLM cục bộ), Next.js (giao diện, sắp có). **Không dùng NestJS, không dùng Redis.**

## Lệnh thường dùng (Windows PowerShell, chạy từ gốc repo)

```powershell
docker compose up -d db                       # chỉ DB
docker compose up --build                     # DB + API (http://localhost:8000/docs)

cd backend
.venv\Scripts\activate
pytest -q                                     # unit + compliance
$env:TEST_DATABASE_URL="postgresql+psycopg://aipi:aipi@localhost:5432/aipi_test"; pytest -q   # thêm test DB
ruff check . ; ruff format .
alembic revision -m "mo_ta" ; alembic upgrade head ; alembic downgrade -1
python -m app.db.seed
```

Lần đầu tạo DB test: `docker compose exec db psql -U aipi -c "create database aipi_test"`.

## Quy ước

- Code và tên biến bằng tiếng Anh. Docstring, comment, thông báo lỗi và tài liệu bằng tiếng Việt.
- Ruff, line length 120. Type hints đầy đủ. Pydantic v2 cho dữ liệu vào/ra.
- Mọi migration phải có `downgrade`. Cột dữ liệu nguồn phải khớp `field_policy.yaml`.
- Mỗi việc trong ROADMAP: viết test trước hoặc cùng lúc. Chỉ đánh `[x]` khi DoD đạt và test, lint xanh.
- Ghi quyết định và kết quả đáng chú ý vào `docs/RESEARCH_LOG.md` (ngày, việc, kết quả, số liệu).
- Không commit `.env`, dữ liệu crawl (`data/raw/`, `data/tmp/`) hay model weights.

## Công cụ Claude Code của dự án

**MCP `aipi`** (chỉ đọc, cấu hình trong `.mcp.json`; cần `backend/.venv` và DB đang chạy cho các tool DB):

| Tool | Dùng khi |
|---|---|
| `roadmap_next` | Bắt đầu phiên: xem việc tiếp theo, DoD và file cần sửa |
| `resolve_ward` | Kiểm tra chuẩn hóa địa chỉ |
| `list_sources` | Xem nguồn nào được crawl và vì sao |
| `check_fields` | Trước khi thêm cột hoặc trường parser |
| `check_robots` | Trước khi thêm nguồn hoặc URL pattern mới |
| `db_schema`, `db_query`, `data_summary` | Xem dữ liệu (SELECT only, READ ONLY, timeout 10 giây) |

**Skills** (`.claude/skills/`): `add-source`, `build-connector`, `db-migration`, `model-experiment`, `weekly-report`, `next-task`.

**Subagents** (`.claude/agents/`):

| Subagent | Việc |
|---|---|
| `compliance-reviewer` | Rà diff theo nguyên tắc bất biến. **Chạy trước khi kết thúc mọi việc chạm vào crawler, schema hoặc dữ liệu.** |
| `connector-engineer` | Viết và sửa connector, parser, normalizer |
| `data-quality-analyst` | Kiểm tra độ phủ, chất lượng, EDA (chỉ đọc) |
| `ml-researcher` | Thí nghiệm định giá và độ uy tín theo đúng quy trình đánh giá |

## Cách bắt đầu một phiên làm việc

1. Gọi `mcp__aipi__roadmap_next` (hoặc đọc `docs/ROADMAP.md`) và chọn việc chưa xong đầu tiên.
2. Đọc DoD và Files của việc đó; đọc code liên quan.
3. Làm, kèm test. Chạy `pytest` và `ruff`.
4. Nếu chạm vào crawler, schema hoặc dữ liệu: gọi subagent `compliance-reviewer`.
5. Đánh `[x]` trong ROADMAP, ghi RESEARCH_LOG, rồi tóm tắt cho người dùng (tiếng Việt).
