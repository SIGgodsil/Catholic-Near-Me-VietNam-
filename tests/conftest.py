"""Test chạy trên một bản DB tạm build từ CSV gốc, không đụng tới data/churches.db và không cần Ollama."""
import os
import tempfile
from pathlib import Path

# Phải đặt trước khi import src.config.
os.environ["CHURCH_DB"] = str(Path(tempfile.mkdtemp()) / "churches_test.db")

from scripts.build_db import build  # noqa: E402
from src.config import DB_PATH, SOURCE_CSV  # noqa: E402

build(SOURCE_CSV, DB_PATH)
