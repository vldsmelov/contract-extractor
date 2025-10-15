import os
from pathlib import Path
from typing import Any, Dict

os.environ.setdefault("USE_LLM", "false")

from fastapi.testclient import TestClient  # type: ignore  # noqa: E402
from app.main import app  # type: ignore  # noqa: E402

client = TestClient(app)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEXT_PATH = ROOT / "sample" / "sample_document.txt"
GOLD_JSON_PATH = ROOT / "test" / "sample_gold.json"


def _load_sample_text() -> str:
    return SAMPLE_TEXT_PATH.read_text(encoding="utf-8")


def test_check_endpoint_accepts_json_payload() -> None:
    payload: Dict[str, Any] = {"text": _load_sample_text()}
    response = client.post("/check", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body.get("data"), dict)
    assert isinstance(body.get("warnings"), list)
    summary = body["data"].get("КраткоеСодержание")
    assert isinstance(summary, str)
    assert 0 < len(summary) <= 300
    justification = body["data"].get("ОбоснованиеВыбора")
    assert isinstance(justification, str)
    assert 0 < len(justification) <= 300


def test_check_endpoint_accepts_file_upload() -> None:
    with SAMPLE_TEXT_PATH.open("rb") as handle:
        files = {"file": (SAMPLE_TEXT_PATH.name, handle.read(), "text/plain")}

    response = client.post("/check", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body.get("data"), dict)
    summary = body["data"].get("КраткоеСодержание")
    assert isinstance(summary, str)
    assert 0 < len(summary) <= 300
    justification = body["data"].get("ОбоснованиеВыбора")
    assert isinstance(justification, str)
    assert 0 < len(justification) <= 300


def test_test_endpoint_handles_multipart_payload() -> None:
    with SAMPLE_TEXT_PATH.open("rb") as text_handle, GOLD_JSON_PATH.open("rb") as gold_handle:
        files = {
            "text_file": (SAMPLE_TEXT_PATH.name, text_handle.read(), "text/plain"),
            "gold_json": (GOLD_JSON_PATH.name, gold_handle.read(), "application/json"),
        }

    response = client.post("/test", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body.get("table"), list)
    assert isinstance(body.get("summary"), dict)
    assert "warnings" in body
