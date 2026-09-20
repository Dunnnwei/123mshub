from __future__ import annotations

import json
from pathlib import Path

from mshub.config import ConfigStore
from mshub.models import SecurityStatus
from mshub.scanner import scan_ai


def test_secrets_never_written_to_plaintext_config(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config")
    store.save({
        "repo_root": str(tmp_path / "repo"),
        "github_token": "ghp_super_secret",
        "ai_key": "sk-super-secret",
    })
    raw = store.path.read_text(encoding="utf-8")
    assert "ghp_super_secret" not in raw
    assert "sk-super-secret" not in raw
    assert json.loads(raw)["github_token_configured"] is True
    assert json.loads(raw)["ai_key_configured"] is True


def test_ai_scanner_retries_without_response_format(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "SKILL.md").write_text("# Safe skill", encoding="utf-8")
    calls = []

    class FakeResponse:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("retry should handle the initial 400")

        def json(self):
            return self._data

    def fake_post(endpoint, *, headers, json, timeout):
        calls.append(json.copy())
        if len(calls) == 1:
            return FakeResponse(400, {})
        return FakeResponse(200, {
            "choices": [{
                "message": {
                    "content": '{"status":"safe","summary":"未发现风险","findings":[]}'
                }
            }]
        })

    monkeypatch.setattr("mshub.scanner.httpx.post", fake_post)
    report = scan_ai(
        tmp_path,
        base_url="https://example.test/v1",
        api_key="secret",
        model="review-model",
    )
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
    assert report.status == SecurityStatus.SAFE

