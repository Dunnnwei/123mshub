import json

from fastapi.testclient import TestClient

from mshub.api import bundled_root, bundled_static_root, create_app
from mshub.config import ConfigStore


def test_first_run_health_and_config(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config")
    client = TestClient(create_app(store))
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["configured"] is False

    response = client.put("/api/config", json={"repo_root": str(tmp_path / "repo")})
    assert response.status_code == 200
    assert response.json()["repo_root"]
    assert client.get("/api/skills").json() == {"items": []}


def test_selecting_synced_repository_recovers_before_rebuilding_index(tmp_path) -> None:
    root = tmp_path / "synced-repo"
    skill_dir = root / "owner__demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    (skill_dir / ".manifest.json").write_text(
        json.dumps({
            "source_url": "https://github.com/owner/demo",
            "commit_hash": "b" * 40,
            "install_mode": "standard",
            "files": [],
        }),
        encoding="utf-8",
    )
    (root / "index.json").write_text(
        json.dumps({
            "skills": [{
                "name": "owner/demo",
                "dir": "owner__demo",
                "tags": ["跨设备"],
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    client = TestClient(create_app(ConfigStore(tmp_path / "fresh-config")))

    response = client.put("/api/config", json={"repo_root": str(root)})

    assert response.status_code == 200
    assert response.json()["recovery"]["recovered_count"] == 1
    assert client.get("/api/skills").json()["items"][0]["tags"] == ["跨设备"]


def test_repository_can_be_reconciled_after_files_are_synced(tmp_path) -> None:
    root = tmp_path / "live-repo"
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(root)})
    client = TestClient(create_app(store))
    skill_dir = root / "owner__later"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Later\n", encoding="utf-8")
    (skill_dir / ".manifest.json").write_text(
        json.dumps({
            "source_url": "https://github.com/owner/later",
            "commit_hash": "d" * 40,
            "install_mode": "standard",
            "files": [],
        }),
        encoding="utf-8",
    )

    response = client.post("/api/repository/reconcile")

    assert response.status_code == 200
    assert response.json()["recovered_count"] == 1
    assert response.json()["total_count"] == 1
    assert client.get("/api/skills").json()["items"][0]["name"] == "owner/later"


def test_migrate_manifests_endpoint_renames_legacy_files(tmp_path) -> None:
    root = tmp_path / "live-repo"
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(root)})
    client = TestClient(create_app(store))
    skill_dir = root / "skills" / "owner__legacy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Legacy\n", encoding="utf-8")
    legacy_payload = json.dumps({
        "source_url": "https://github.com/owner/legacy",
        "commit_hash": "e" * 40,
        "install_mode": "standard",
        "files": [],
        "scan": {"status": "warning", "route": "offline", "findings": []},
    })
    (skill_dir / ".manifest.json").write_text(legacy_payload, encoding="utf-8")

    response = client.post("/api/repository/migrate-manifests")

    assert response.status_code == 200
    assert response.json()["migrated"] == 1
    assert not (skill_dir / ".manifest.json").exists()
    assert (skill_dir / "_manifest.json").is_file()
    assert (skill_dir / "_manifest.json").read_text(encoding="utf-8") == legacy_payload


def test_api_returns_safe_validation_error(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config")
    client = TestClient(create_app(store))
    response = client.get("/api/skills")
    assert response.status_code == 400
    assert "仓库根目录" in response.json()["detail"]


def test_ai_provider_presets_include_common_openai_compatible_services(tmp_path) -> None:
    client = TestClient(create_app(ConfigStore(tmp_path / "config")))

    response = client.get("/api/config/ai-presets")

    assert response.status_code == 200
    presets = {item["id"]: item for item in response.json()["items"]}
    assert set(presets) >= {
        "openai", "deepseek", "openrouter", "siliconflow", "zhipu", "dashscope",
    }
    assert presets["deepseek"]["base_url"] == "https://api.deepseek.com"
    assert presets["zhipu"]["model"] == "glm-5.2"


def test_help_route_serves_utf8_readme(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config")
    client = TestClient(create_app(store))
    response = client.get("/api/help")
    assert response.status_code == 200
    assert "123 MSHub（Memory & Skill Hub）" in response.text
    assert "共享大脑管理器" in response.text


def test_api_installs_and_updates_tags(tmp_path, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))

    installed = client.post(
        "/api/skills",
        json={"source": "owner/demo", "tags": ["自动化", " Python ", "python"]},
    )
    assert installed.status_code == 200
    assert installed.json()["tags"] == ["自动化", "Python"]

    changed = client.put(
        "/api/skills/tags",
        json={"name": "owner/demo", "tags": ["Agent", "开发"]},
    )
    assert changed.status_code == 200
    assert changed.json()["tags"] == ["Agent", "开发"]
    assert client.get("/api/tags").json() == {
        "items": [
            {"name": "Agent", "count": 1},
            {"name": "开发", "count": 1},
        ],
        "untagged_count": 0,
    }


def test_api_accepts_project_clone_type(tmp_path, fake_fetcher, monkeypatch) -> None:
    fake_fetcher.name = "git"
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))

    response = client.post(
        "/api/skills",
        json={"source": "owner/app", "item_type": "project", "mode": "standard"},
    )

    assert response.status_code == 200
    assert response.json()["item_type"] == "project"
    assert response.json()["install_mode"] == "full"


def test_pyinstaller_bundle_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("mshub.api.sys.frozen", True, raising=False)
    monkeypatch.setattr("mshub.api.sys._MEIPASS", str(tmp_path), raising=False)
    assert bundled_root() == tmp_path
    assert bundled_static_root() == tmp_path / "mshub" / "web"


def _wait_job_done(client, job_id: str, timeout: float = 10.0) -> dict:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()["items"]
        job = next((item for item in jobs if item["id"] == job_id), None)
        if job and job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("后台任务超时未完成")


def test_install_job_runs_in_background_and_reports_progress(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))

    response = client.post("/api/jobs/install", json={"source": "owner/demo"})

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    job = _wait_job_done(client, job_id)
    assert job["status"] == "done"
    assert job["progress"] == 100
    names = [item["name"] for item in client.get("/api/skills").json()["items"]]
    assert "owner/demo" in names


def test_failed_job_reports_error_without_crashing(tmp_path, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr(
        "mshub.repository.get_fetcher",
        lambda _: monkeypatch_raise(),
    )

    class _Raiser:
        name = "archive"

        def fetch(self, *args, **kwargs):
            from mshub.errors import FetchError

            raise FetchError("模拟下载失败")

    def monkeypatch_raise():
        return _Raiser()

    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))

    response = client.post("/api/jobs/install", json={"source": "owner/demo"})

    job = _wait_job_done(client, response.json()["job_id"])
    assert job["status"] == "error"
    assert "模拟下载失败" in job["error"]
    assert client.get("/api/skills").json()["items"] == []


def test_scan_job_returns_report_in_result(tmp_path, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})

    response = client.post("/api/jobs/scan", json={"name": "owner/demo", "route": "offline"})

    job = _wait_job_done(client, response.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["name"] == "owner/demo"
    assert job["result"]["status"] in {"safe", "warning"}


def test_config_returns_masked_secrets_only(tmp_path) -> None:
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo"), "github_token": "ghp_abcdefgh12345678"})
    client = TestClient(create_app(store))

    response = client.get("/api/config").json()

    assert response["github_token_masked"] == "ghp_••••••5678"
    assert "ghp_abcdefgh12345678" not in str(response)
    assert response["ai_key_masked"] == ""


def test_trust_marks_skill_safe_and_persists(tmp_path, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})

    response = client.post("/api/skills/trust", json={"name": "owner/demo"})

    assert response.status_code == 200
    assert response.json()["security_status"] == "safe"
    assert response.json()["security_route"] == "trust"
    listed = client.get("/api/skills").json()["items"][0]
    assert listed["security_status"] == "safe"


def test_ai_models_endpoint_lists_gateway_models(tmp_path, monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    captured = {}

    def fake_get(endpoint, headers=None, **kwargs):
        captured["endpoint"] = endpoint
        captured["headers"] = headers
        return FakeResponse({"data": [{"id": "glm-5.3"}, {"id": "v4-flash"}, {"id": "glm-5.3"}]})

    monkeypatch.setattr("mshub.api.httpx.get", fake_get)
    client = TestClient(create_app(ConfigStore(tmp_path / "config")))

    response = client.post("/api/ai/models", json={"ai_base_url": "http://192.0.2.10:3000/v1", "ai_key": "tk"})

    assert response.status_code == 200
    assert response.json()["items"] == ["glm-5.3", "v4-flash"]
    assert captured["endpoint"] == "http://192.0.2.10:3000/v1/models"
    assert captured["headers"]["Authorization"] == "Bearer tk"


def test_update_metadata_renames_entry_and_moves_directory(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})

    response = client.put(
        "/api/skills/metadata",
        json={
            "name": "owner/demo",
            "new_name": "owner/demo-renamed",
            "description": "手工修正后的备注",
            "dir_name": "owner__demo-v2",
            "version": "9.9.9",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "owner/demo-renamed"
    assert body["description"] == "手工修正后的备注"
    assert body["version"] == "9.9.9"
    assert body["local_dir"] == "owner__demo-v2"
    assert (tmp_path / "repo" / "owner__demo-v2" / "SKILL.md").is_file()
    assert not (tmp_path / "repo" / "owner__demo").exists()
    names = [item["name"] for item in client.get("/api/skills").json()["items"]]
    assert names == ["owner/demo-renamed"]
    index = json.loads((tmp_path / "repo" / "index.json").read_text(encoding="utf-8"))
    assert index["skills"][0]["name"] == "owner/demo-renamed"
    assert index["skills"][0]["description_zh"] == "手工修正后的备注"


def test_update_metadata_fixes_wrong_local_source_to_github(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})

    # 先改成 local（模拟被误判为自研），再修正回 GitHub 原仓（含 monorepo 子目录）。
    client.put("/api/skills/metadata", json={"name": "owner/demo", "provider": "local"})
    local = client.get("/api/skills").json()["items"][0]
    assert local["provider"] == "local"
    assert local["source_url"] == ""

    fixed = client.put(
        "/api/skills/metadata",
        json={
            "name": "owner/demo",
            "provider": "github",
            "source_url": "https://github.com/anthropics/skills/tree/main/skills/docx",
        },
    )

    assert fixed.status_code == 200
    body = fixed.json()
    assert body["provider"] == "github"
    assert body["author"] == "anthropics"
    assert body["repo"] == "skills"
    assert body["subdir"] == "skills/docx"
    manifest = json.loads(
        (tmp_path / "repo" / "owner__demo" / "_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_type"] == "github"
    assert manifest["subdir"] == "skills/docx"


def test_update_metadata_decouples_name_from_directory(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    """身份与归属分离：改目录名只移动磁盘目录，条目名独立可改。"""
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo", "library": "skills"})

    renamed = client.put(
        "/api/skills/metadata",
        json={"name": "owner/demo", "library": "skills", "dir_name": "demo-skill"},
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "owner/demo"
    assert renamed.json()["local_dir"] == "skills/demo-skill"
    assert (tmp_path / "repo" / "skills" / "demo-skill" / "SKILL.md").is_file()
    manifest = json.loads(
        (tmp_path / "repo" / "skills" / "demo-skill" / "_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "owner/demo"

    # 条目名可以自由改身份，不影响目录与库
    retitled = client.put(
        "/api/skills/metadata",
        json={"name": "owner/demo", "library": "skills", "new_name": "owner/demo-pro"},
    )
    assert retitled.status_code == 200
    assert retitled.json()["name"] == "owner/demo-pro"
    assert retitled.json()["local_dir"] == "skills/demo-skill"

    # 同库重名被拒绝
    client.post("/api/skills", json={"source": "owner/other", "library": "skills"})
    clash = client.put(
        "/api/skills/metadata",
        json={"name": "owner/other", "library": "skills", "new_name": "owner/demo-pro"},
    )
    assert clash.status_code == 409


def test_translate_one_stores_chinese_description(tmp_path, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})
    client.put(
        "/api/skills/metadata",
        json={"name": "owner/demo", "description": "An English description for testing."},
    )

    def fake_translate(text, *, base_url, api_key, model=""):
        return "一条用于测试的中文备注。"

    monkeypatch.setattr("mshub.repository.translate_description", fake_translate)

    response = client.post("/api/skills/translate", json={"name": "owner/demo"})

    assert response.status_code == 200
    assert response.json()["description_zh"] == "一条用于测试的中文备注。"
    listed = client.get("/api/skills").json()["items"][0]
    assert listed["description_zh"] == "一条用于测试的中文备注。"
    manifest = json.loads(
        (tmp_path / "repo" / "owner__demo" / "_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["description_zh"] == "一条用于测试的中文备注。"


def test_translate_native_chinese_description_skips_gateway(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    installed = client.post("/api/skills", json={"source": "owner/demo"})
    assert is_native_chinese(installed.json()["description"])

    def fail_translate(*args, **kwargs):
        raise AssertionError("原生中文备注不应调用网关")

    monkeypatch.setattr("mshub.repository.translate_description", fail_translate)

    response = client.post("/api/skills/translate", json={"name": "owner/demo"})

    assert response.status_code == 200
    assert response.json()["description_zh"] == installed.json()["description"]


def test_translate_batch_job_marks_native_and_translates_missing(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.set_secret("ai_key", "tk")
    store.save({"repo_root": str(tmp_path / "repo"), "ai_base_url": "http://gateway/v1"})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})
    client.put(
        "/api/skills/metadata",
        json={"name": "owner/demo", "description": "Another English description."},
    )

    def fake_translate(text, *, base_url, api_key, model=""):
        return f"【译】{text}"

    monkeypatch.setattr("mshub.repository.translate_description", fake_translate)

    response = client.post("/api/jobs/translate", json={})

    job = _wait_job_done(client, response.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["translated"] == 1
    listed = client.get("/api/skills").json()["items"][0]
    assert listed["description_zh"] == "【译】Another English description."


def is_native_chinese(text: str) -> bool:
    from mshub.translation import is_mostly_chinese

    return is_mostly_chinese(text)


def test_manifest_edit_from_other_machine_backfills_on_reconcile(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})
    # 模拟另一台机器直接改了随目录同步的 manifest（走 patch_manifest 语义）
    skill_dir = tmp_path / "repo" / "owner__demo"
    patch = json.loads((skill_dir / "_manifest.json").read_text(encoding="utf-8"))
    patch.update({
        "description": "对端机器修正后的备注",
        "description_zh": "对端机器修正后的中文备注",
        "source_type": "github",
        "source_url": "https://github.com/other/renamed",
        "tags": ["对端标签"],
        "generated_at": "2099-01-01T00:00:00+00:00",
    })
    (skill_dir / "_manifest.json").write_text(
        json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    reconciled = client.post("/api/repository/reconcile").json()

    assert reconciled["backfilled_count"] == 1
    listed = client.get("/api/skills").json()["items"][0]
    assert listed["description"] == "对端机器修正后的备注"
    assert listed["description_zh"] == "对端机器修正后的中文备注"
    assert listed["source_url"] == "https://github.com/other/renamed"
    assert listed["author"] == "other"
    assert listed["repo"] == "renamed"
    assert listed["tags"] == ["对端标签"]
    # 幂等：再跑一次不再计数
    assert client.post("/api/repository/reconcile").json()["backfilled_count"] == 0


def test_backfill_ignores_manifest_not_newer_than_local(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})

    reconciled = client.post("/api/repository/reconcile").json()

    # 本机刚安装：manifest 与 DB 同秒写入，manifest 不新于 DB，不应回填
    assert reconciled["backfilled_count"] == 0


def test_set_tags_writes_manifest_for_cross_machine_sync(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})

    client.put("/api/skills/tags", json={"name": "owner/demo", "tags": ["跨机"]})

    manifest = json.loads(
        (tmp_path / "repo" / "owner__demo" / "_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["tags"] == ["跨机"]
    assert manifest["generated_at"] > "2026"


def test_index_rebuild_is_silent_when_library_unchanged(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo"})
    index_path = tmp_path / "repo" / "index.json"
    before = index_path.read_bytes()

    assert client.post("/api/index/rebuild").status_code == 200
    assert client.post("/api/index/rebuild").status_code == 200

    # 技能清单没变：文件一个字节都不动（含 generated_at），不给同步盘制造事件
    assert index_path.read_bytes() == before

    client.put("/api/skills/tags", json={"name": "owner/demo", "tags": ["真实变更"]})
    after = json.loads(index_path.read_text(encoding="utf-8"))
    assert after["skills"][0]["tags"] == ["真实变更"]
    assert index_path.read_bytes() != before


def test_classify_repository_detects_skill_program_and_monorepo(tmp_path) -> None:
    from mshub.parser import classify_repository

    skill_root = tmp_path / "skill-repo"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("---\nname: demo\n---", encoding="utf-8")
    result = classify_repository(skill_root)
    assert result["suggested_item_type"] == "skill"

    program_root = tmp_path / "program-repo"
    program_root.mkdir()
    (program_root / "package.json").write_text("{}", encoding="utf-8")
    result = classify_repository(program_root)
    assert result["suggested_item_type"] == "project"
    assert "package.json" in result["suggestion_reason"]

    monorepo = tmp_path / "monorepo"
    (monorepo / "skills" / "docx").mkdir(parents=True)
    (monorepo / "skills" / "docx" / "SKILL.md").write_text("x", encoding="utf-8")
    result = classify_repository(monorepo)
    assert result["suggested_item_type"] == "project"
    assert result["skill_subdirs"] == ["skills/docx"]


def test_preview_carries_type_suggestion(tmp_path, fake_fetcher, monkeypatch) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))

    preview = client.post("/api/skills/preview", json={"source": "owner/demo"}).json()

    assert preview["suggested_item_type"] == "skill"
    assert "SKILL.md" in preview["suggestion_reason"]


def test_update_metadata_moves_item_between_libraries(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    """下载错了库的修复：编辑信息里切换所属库，目录/记录/manifest 一起搬。"""
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))
    client.post("/api/skills", json={"source": "owner/demo", "library": "skills"})

    moved = client.put(
        "/api/skills/metadata",
        json={"name": "owner/demo", "library": "skills", "target_library": "github"},
    )

    assert moved.status_code == 200
    assert moved.json()["library"] == "github"
    assert moved.json()["local_dir"] == "github/owner__demo"
    assert (tmp_path / "repo" / "github" / "owner__demo" / "SKILL.md").is_file()
    assert not (tmp_path / "repo" / "skills" / "owner__demo").exists()
    manifest = json.loads(
        (tmp_path / "repo" / "github" / "owner__demo" / "_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["library"] == "github"
    listed = client.get("/api/skills").json()["items"][0]
    assert listed["library"] == "github"

    # 搬回去
    back = client.put(
        "/api/skills/metadata",
        json={"name": "owner/demo", "library": "github", "target_library": "skills"},
    )
    assert back.status_code == 200
    assert back.json()["local_dir"] == "skills/owner__demo"


def test_git_auth_header_uses_basic_format() -> None:
    """GitHub git 通道只认 Basic：Bearer 会被拒（公司分机 2026-09-10 实测确证）。"""
    import base64

    from mshub.fetcher import _git_auth_header

    header = _git_auth_header("ghp_test123")
    assert header.startswith("AUTHORIZATION: basic ")
    payload = base64.b64decode(header.split(" ", 2)[2]).decode("utf-8")
    assert payload == "x-access-token:ghp_test123"


def test_job_dismiss_removes_finished_and_orders_newest_first(
    tmp_path, fake_fetcher, monkeypatch
) -> None:
    monkeypatch.setattr("mshub.repository.get_fetcher", lambda _: fake_fetcher)
    store = ConfigStore(tmp_path / "config")
    store.save({"repo_root": str(tmp_path / "repo")})
    client = TestClient(create_app(store))

    first = client.post("/api/jobs/install", json={"source": "owner/demo"}).json()["job_id"]
    first_done = _wait_job_done(client, first)
    assert first_done["status"] == "done"

    fake_fetcher.revision = 2
    second = client.post("/api/jobs/install", json={"source": "owner/demo", "overwrite": True}).json()["job_id"]
    _wait_job_done(client, second)

    items = client.get("/api/jobs").json()["items"]
    assert len(items) == 2
    # 已完成任务按创建时间倒序：最新的在最前
    assert items[0]["id"] == second
    assert items[1]["id"] == first

    # X 关闭：服务端删除，重开面板不再出现
    response = client.post("/api/jobs/dismiss", json={"job_id": second})
    assert response.status_code == 200
    items = client.get("/api/jobs").json()["items"]
    assert [item["id"] for item in items] == [first]

    # 一键清除已完成
    assert client.post("/api/jobs/clear-finished").json()["cleared"] == 1
    assert client.get("/api/jobs").json()["items"] == []
