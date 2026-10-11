# PostgreSQL 16 + pgvector + PostGIS 3, trên Debian 12 (bookworm).
# Không dùng postgis/postgis:16-3.5 vì image đó chạy trên Debian 11 (bullseye) đã hết hỗ trợ -> apt-get lỗi.
FROM pgvector/pgvector:0.8.1-pg16-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-postgis-3 postgresql-16-postgis-3-scripts \
 && rm -rf /var/lib/apt/lists/*
