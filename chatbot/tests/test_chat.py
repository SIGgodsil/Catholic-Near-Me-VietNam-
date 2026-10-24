"""Chatbot qua API và câu hỏi "gần tôi". Phần LLM được giả lập để test không cần Ollama."""
import pytest
from fastapi.testclient import TestClient

import server.main as main
import src.bot as bot
from src.db import Filters, churches

client = TestClient(main.app)

TAN_DINH = (10.7884, 106.6906)
HA_NOI = (21.0285, 105.8542)


@pytest.fixture
def fake_llm(monkeypatch):
    """Giả lập extract(): mọi câu hỏi đều thành bộ lọc 'liệt kê', không có tên/địa điểm."""
    monkeypatch.setattr(bot, "extract", lambda q, model=None: (Filters(intent="liet_ke"), {}))


# ---------- "gần tôi" trong module dùng chung ----------

def test_near_me_without_location_asks_back(fake_llm):
    r = bot.answer("nhà thờ gần tôi")
    assert r.status == "clarify" and "vị trí" in r.text


def test_near_me_lists_churches_within_3km_nearest_first(fake_llm):
    r = bot.answer("nhà thờ gần tôi", near=TAN_DINH)
    assert r.status == "ok" and r.hits
    dists = [h.distance_km for h in r.hits]
    assert all(d <= 3 for d in dists) and dists == sorted(dists)
    assert "bán kính 3 km" in r.text
    # Nhiều hơn 8 nhà thờ thì chi tiết nằm trong bảng, có cột khoảng cách.
    assert len(r.hits) > 8 and all("Khoảng cách" in row for row in r.table)
    assert r.table[0]["Nhà thờ"] == r.hits[0].name


def test_near_me_far_away(fake_llm):
    r = bot.answer("nhà thờ nào gần đây", near=HA_NOI)
    assert r.status == "not_found" and "3 km" in r.text


def test_follow_up_keeps_nearby_churches(fake_llm):
    first = bot.answer("nhà thờ gần tôi", near=TAN_DINH)
    again = bot.answer("trong đó nhà thờ nào có lễ", near=TAN_DINH, context=first.context)
    assert {h.id for h in again.hits} <= {h.id for h in first.hits}


# ---------- API ----------

def test_chat_api_session_and_location(monkeypatch):
    seen = {}

    def fake_answer(q, context=None, near=None):
        seen.update(q=q, context=context, near=near)
        return bot.BotResponse("Trả lời thử", status="ok", context="ctx")

    monkeypatch.setattr(main, "answer", fake_answer)
    r1 = client.post("/api/chat", json={"message": "  xin chào  ", "lat": TAN_DINH[0], "lon": TAN_DINH[1]}).json()
    assert r1["reply"] == "Trả lời thử" and len(r1["session_id"]) == 32
    assert seen["q"] == "xin chào" and seen["near"] == TAN_DINH and seen["context"] is None

    client.post("/api/chat", json={"message": "tiếp", "session_id": r1["session_id"]})
    assert seen["context"] == "ctx" and seen["near"] is None

    client.post("/api/chat/reset", json={"session_id": r1["session_id"]})
    client.post("/api/chat", json={"message": "lại", "session_id": r1["session_id"]})
    assert seen["context"] is None


def test_chat_api_ollama_down(monkeypatch):
    def down(*a, **kw):
        raise ConnectionError("Failed to connect to Ollama")

    monkeypatch.setattr(main, "answer", down)
    r = client.post("/api/chat", json={"message": "giờ lễ Tân Định"})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]


def test_chat_api_rejects_empty_and_too_long():
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "a" * 501}).status_code == 422


def test_chat_api_ignores_malformed_session_id(monkeypatch):
    monkeypatch.setattr(main, "answer", lambda q, context=None, near=None: bot.BotResponse("ok"))
    r = client.post("/api/chat", json={"message": "hi", "session_id": "../../etc"}).json()
    assert r["session_id"] != "../../etc" and len(r["session_id"]) == 32


def test_church_count_matches_scope_note():
    # SCOPE_NOTE ghi cứng số nhà thờ; nhắc cập nhật khi đổi dataset.
    assert f"{len(churches())} nhà thờ" in bot.SCOPE_NOTE


def test_toi_nay_means_today():
    import datetime as dt

    from src.extract import rule_days
    sun = dt.date(2026, 10, 25)
    assert rule_days("nhà thờ nào có lễ tối nay", today=sun) == [6]
    assert rule_days("le sang nay o go vap", today=sun) == [6]
    assert rule_days("lễ tối thứ 7", today=sun) == [5]
