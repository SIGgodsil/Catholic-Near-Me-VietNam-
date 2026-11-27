import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Dataset gốc chỉ được đọc, không bao giờ ghi.
SOURCE_CSV = Path(os.getenv(
    "CHURCH_CSV",
    ROOT / "data" / "processed" / "catholic_churches_complete.csv",
))
DB_PATH = Path(os.getenv("CHURCH_DB", ROOT / "data" / "churches.db"))

# Lấy key miễn phí tại https://aistudio.google.com/apikey. Không đưa key vào Git.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "30"))
