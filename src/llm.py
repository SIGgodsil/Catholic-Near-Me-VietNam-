"""Gọi Gemini API (REST) cho chatbot. Key chỉ nằm ở server, trình duyệt không bao giờ thấy."""
import time

import httpx

from .config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_DELAYS = (1, 3)


class LLMError(Exception):
    """Không gọi được Gemini: thiếu key, hết hạn mức miễn phí, mạng lỗi hoặc trả về rỗng."""

    def __init__(self, message: str, quota: bool = False):
        super().__init__(message)
        self.quota = quota


def generate(system: str, user: str, model: str = GEMINI_MODEL, temperature: float = 0,
             max_tokens: int | None = None, json_schema: dict | None = None) -> str:
    if not GEMINI_API_KEY:
        raise LLMError("Chưa đặt biến môi trường GEMINI_API_KEY")
    config: dict = {"temperature": temperature}
    if max_tokens:
        config["maxOutputTokens"] = max_tokens
    if json_schema:
        config |= {"responseMimeType": "application/json", "responseJsonSchema": json_schema}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": config,
    }
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            r = httpx.post(API_URL.format(model=model), json=body, timeout=GEMINI_TIMEOUT,
                           headers={"x-goog-api-key": GEMINI_API_KEY})
        except httpx.HTTPError as e:
            raise LLMError(f"Không kết nối được Gemini: {e!r}") from e
        # 500/503: Google quá tải tạm thời, thường hết sau vài giây.
        if r.status_code not in (500, 503) or attempt == len(RETRY_DELAYS):
            break
        time.sleep(RETRY_DELAYS[attempt])
    if r.status_code == 429:
        raise LLMError("Gemini báo hết hạn mức (429)", quota=True)
    if r.status_code != 200:
        raise LLMError(f"Gemini trả về {r.status_code}: {r.text[:300]}")
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"Gemini trả về dữ liệu lạ: {r.text[:300]}") from e
    if not text.strip():
        raise LLMError("Gemini trả về rỗng")
    return text
