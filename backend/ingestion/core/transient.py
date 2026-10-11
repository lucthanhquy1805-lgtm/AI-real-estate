"""Thư mục tạm cho một job (nguyên tắc 3: mô tả và ảnh chỉ được xử lý tạm rồi xóa).

Dùng làm context manager: thư mục luôn bị xóa khi ra khỏi khối `with`, kể cả khi có lỗi.
`sweep()` dọn thư mục còn sót lại từ job bị kill giữa chừng; job runner gọi nó trước mỗi lần chạy.
"""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from app.config import get_settings


def _force_remove(func: Callable[[str], object], path: str, _exc: BaseException) -> None:
    # Windows: file chỉ-đọc làm rmtree thất bại; bỏ thuộc tính read-only rồi thử lại.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_force_remove)


class TransientStore:
    def __init__(self, job_id: str | uuid.UUID | None = None, root: Path | None = None):
        self.root = Path(root) if root is not None else get_settings().transient_dir
        self.job_id = str(job_id or uuid.uuid4())
        self.path = self.root / self.job_id
        self._open = False

    def __enter__(self) -> TransientStore:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.mkdir()
        self._open = True
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        self._open = False
        _rmtree(self.path)

    def _resolve(self, name: str) -> Path:
        if not self._open:
            raise RuntimeError("TransientStore chưa mở hoặc đã đóng")
        p = (self.path / name).resolve()
        if self.path.resolve() not in p.parents:
            raise ValueError(f"Tên file tạm không hợp lệ: {name!r}")
        return p

    def write_bytes(self, name: str, data: bytes) -> Path:
        p = self._resolve(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def write_text(self, name: str, text: str) -> Path:
        return self.write_bytes(name, text.encode("utf-8"))

    def is_empty(self) -> bool:
        return not self.path.exists() or not any(self.path.iterdir())

    @staticmethod
    def sweep(root: Path | None = None) -> int:
        """Xóa mọi thư mục job còn sót trong `root`. Trả về số thư mục đã xóa."""
        root = Path(root) if root is not None else get_settings().transient_dir
        if not root.exists():
            return 0
        n = 0
        for child in root.iterdir():
            if child.is_dir():
                _rmtree(child)
            else:
                child.unlink()
            n += 1
        return n
