from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_repo_root() -> Path:
    # backend/app/config.py -> repo root là 2 cấp trên thư mục backend
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Đọc .env ở gốc repo dù chạy lệnh từ thư mục nào (vd backend/); .env trong thư mục hiện tại ghi đè nếu có.
    model_config = SettingsConfigDict(
        env_file=(_default_repo_root() / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://aipi:aipi@localhost:55432/aipi"
    repo_root: Path = _default_repo_root()
    # Khóa HMAC cho pseudonym người đăng. Không commit; đặt trong .env.
    poster_hmac_key: str = ""
    environment: str = "local"

    @property
    def contracts_dir(self) -> Path:
        return self.repo_root / "packages" / "contracts"

    @property
    def reference_dir(self) -> Path:
        return self.repo_root / "data" / "reference"


@lru_cache
def get_settings() -> Settings:
    return Settings()
