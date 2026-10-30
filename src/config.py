import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Dataset gốc chỉ được đọc, không bao giờ ghi.
SOURCE_CSV = Path(os.getenv(
    "CHURCH_CSV",
    ROOT / "data" / "processed" / "catholic_churches_complete.csv",
))
DB_PATH = Path(os.getenv("CHURCH_DB", ROOT / "data" / "churches.db"))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# Lần gọi đầu phải nạp model vào RAM nên có thể mất vài chục giây trên CPU.
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))
