FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 REPO_ROOT=/repo
WORKDIR /repo/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/ingestion ./ingestion
RUN pip install --no-cache-dir -e ".[dev]"
COPY backend ./
COPY packages /repo/packages
COPY data/reference /repo/data/reference
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.db.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
