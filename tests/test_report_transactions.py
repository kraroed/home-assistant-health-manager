import asyncio
import importlib.util
import sys
import threading
import types
from pathlib import Path


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "home_assistant_health_manager"

package = types.ModuleType("health_manager_report_test")
package.__path__ = []
sys.modules[package.__name__] = package
const = types.ModuleType("health_manager_report_test.const")
const.DOMAIN = "home_assistant_health_manager"
const.REPORT_DIR = "health_manager/reports"
sys.modules[const.__name__] = const

spec = importlib.util.spec_from_file_location(
    "health_manager_report_test.report", INTEGRATION / "report.py"
)
REPORT = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = REPORT
spec.loader.exec_module(REPORT)


def _make_report_artifacts(directory, base):
    for suffix in (".json", ".txt", ".zip", "_ai_repair_prompt.md"):
        (directory / f"{base}{suffix}").write_text("report artifact", encoding="utf-8")


def test_reconcile_removes_uncommitted_partial_report(tmp_path):
    base = "health_report_20261115T120000000000Z"
    _make_report_artifacts(tmp_path, base)
    (tmp_path / f".{base}.pending").touch()
    staging = tmp_path / ".health_report_abandoned"
    staging.mkdir()
    (staging / "partial").write_text("partial", encoding="utf-8")

    REPORT._reconcile_report_transactions_sync(tmp_path, None)

    assert not list(tmp_path.glob(f"{base}*"))
    assert not (tmp_path / f".{base}.pending").exists()
    assert not staging.exists()


def test_reconcile_finalizes_report_committed_before_restart(tmp_path):
    base = "health_report_20261115T120000000000Z"
    _make_report_artifacts(tmp_path, base)
    (tmp_path / f".{base}.pending").touch()

    REPORT._reconcile_report_transactions_sync(tmp_path, str(tmp_path / f"{base}.zip"))

    assert (tmp_path / f"{base}.zip").exists()
    assert (tmp_path / f".{base}.complete").exists()
    assert not (tmp_path / f".{base}.pending").exists()



def test_reconcile_removes_focused_prompt_not_committed_to_store(tmp_path):
    prompt = "focused_repair_mqtt_20261115T120000000000Z.md"
    (tmp_path / prompt).write_text("prompt", encoding="utf-8")
    (tmp_path / f".{prompt}.pending").touch()

    REPORT._reconcile_focused_prompt_transactions_sync(tmp_path, set())

    assert not (tmp_path / prompt).exists()
    assert not (tmp_path / f".{prompt}.pending").exists()


def test_reconcile_preserves_focused_prompt_committed_to_store(tmp_path):
    prompt = "focused_repair_mqtt_20261115T120000000000Z.md"
    (tmp_path / prompt).write_text("prompt", encoding="utf-8")
    (tmp_path / f".{prompt}.pending").touch()

    REPORT._reconcile_focused_prompt_transactions_sync(tmp_path, {prompt})

    assert (tmp_path / prompt).read_text(encoding="utf-8") == "prompt"
    assert not (tmp_path / f".{prompt}.pending").exists()



def _write_report(REPORT, directory, **overrides):
    values = {
        "directory_path": directory,
        "snapshot": {"collected_at": "2026-11-15T12:00:00+00:00", "entity_count": 1},
        "analysis": {"assessment_type": "weekly_diagnostic", "level_counts": {}},
        "sanitized_log": None,
        "redaction_counts": {},
        "recommendations": [],
        "issue_history": {},
        "issue_summary": {},
        "repair_prompt": "Review diagnostics carefully.",
        "compatibility": {},
        "change_summary": {},
        "retention_days": 90,
    }
    values.update(overrides)
    return REPORT._write_report_sync(**values)


def test_report_staging_failure_leaves_no_published_artifacts_or_marker(tmp_path, monkeypatch):
    def fail_zip(*args, **kwargs):
        raise OSError("simulated ZIP write failure")

    monkeypatch.setattr(REPORT.zipfile, "ZipFile", fail_zip)

    try:
        _write_report(REPORT, tmp_path)
    except OSError as err:
        assert "simulated ZIP write failure" in str(err)
    else:
        raise AssertionError("expected ZIP write failure")

    assert not list(tmp_path.glob("health_report_*"))
    assert not list(tmp_path.glob(".health_report_*.pending"))
    assert not list(tmp_path.glob(".health_report_*"))


def test_partial_publication_is_removed_during_reconciliation(tmp_path, monkeypatch):
    original_replace = REPORT.os.replace
    calls = {"count": 0}

    def fail_during_publish(source, destination):
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("simulated publication interruption")
        return original_replace(source, destination)

    monkeypatch.setattr(REPORT.os, "replace", fail_during_publish)

    try:
        _write_report(REPORT, tmp_path)
    except OSError as err:
        assert "simulated publication interruption" in str(err)
    else:
        raise AssertionError("expected publication failure")

    pending = list(tmp_path.glob(".health_report_*.pending"))
    assert len(pending) == 1
    assert list(tmp_path.glob("health_report_*"))

    REPORT._reconcile_report_transactions_sync(tmp_path, None)

    assert not list(tmp_path.glob("health_report_*"))
    assert not list(tmp_path.glob(".health_report_*.pending"))


def test_committed_report_survives_reconciliation_and_retention_cleanup(tmp_path):
    old = tmp_path / "health_report_20200101T000000000000Z.zip"
    old.write_text("old", encoding="utf-8")
    import os
    import time
    old_time = time.time() - 400 * 24 * 60 * 60
    os.utime(old, (old_time, old_time))

    path = _write_report(REPORT, tmp_path, retention_days=90)
    assert Path(path).exists()
    assert not old.exists()

    REPORT._reconcile_report_transactions_sync(tmp_path, path)

    assert Path(path).exists()
    assert Path(path).with_name(f".{Path(path).stem}.complete").exists()


def test_cancelled_report_writer_removes_artifacts_after_worker_finishes(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    base = "health_report_cancelled"

    def slow_writer(directory, *args):
        directory = Path(directory)
        for suffix in (".json", ".txt", ".zip", "_ai_repair_prompt.md"):
            (directory / f"{base}{suffix}").write_text("partial", encoding="utf-8")
        (directory / f".{base}.pending").touch()
        started.set()
        release.wait(timeout=5)
        return str(directory / f"{base}.zip")

    monkeypatch.setattr(REPORT, "_write_report_sync", slow_writer)
    hass = types.SimpleNamespace(
        data={}, config=types.SimpleNamespace(path=lambda value: str(tmp_path))
    )

    async def run():
        task = asyncio.create_task(REPORT.write_report(
            hass, {}, {}, None, {}, []
        ))
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("expected cancellation")

    asyncio.run(run())
    assert not list(tmp_path.glob(f"{base}*"))
    assert not (tmp_path / f".{base}.pending").exists()


def test_cancelled_focused_prompt_writer_removes_artifacts_after_worker_finishes(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_writer(directory, safe_id, stamp, prompt, retention_days):
        directory = Path(directory)
        path = directory / f"focused_repair_{safe_id}_{stamp}.md"
        path.with_name(f".{path.name}.pending").touch()
        path.write_text(prompt, encoding="utf-8")
        started.set()
        release.wait(timeout=5)
        return str(path)

    monkeypatch.setattr(REPORT, "_write_focused_prompt_sync", slow_writer)
    hass = types.SimpleNamespace(
        data={}, config=types.SimpleNamespace(path=lambda value: str(tmp_path))
    )

    async def run():
        task = asyncio.create_task(REPORT.write_focused_repair_prompt(
            hass, "mqtt", "Review this repair"
        ))
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("expected cancellation")

    asyncio.run(run())
    assert not list(tmp_path.glob("focused_repair_*.md"))
    assert not list(tmp_path.glob(".focused_repair_*.pending"))



def test_retention_removes_every_expired_report_artifact_and_completion_marker(tmp_path):
    base = "health_report_20200101T000000000000Z"
    _make_report_artifacts(tmp_path, base)
    complete = tmp_path / f".{base}.complete"
    complete.touch()
    import os
    import time
    old_time = time.time() - 400 * 24 * 60 * 60
    for artifact in list(tmp_path.glob(f"{base}*")) + [complete]:
        os.utime(artifact, (old_time, old_time))

    new_path = _write_report(REPORT, tmp_path, retention_days=90)

    assert Path(new_path).exists()
    assert not list(tmp_path.glob(f"{base}*"))
    assert not complete.exists()


def test_retention_does_not_delete_pending_transaction_marker(tmp_path):
    base = "health_report_20200101T000000000000Z"
    _make_report_artifacts(tmp_path, base)
    pending = tmp_path / f".{base}.pending"
    pending.touch()
    import os
    import time
    old_time = time.time() - 400 * 24 * 60 * 60
    for artifact in list(tmp_path.glob(f"{base}*")) + [pending]:
        os.utime(artifact, (old_time, old_time))

    _write_report(REPORT, tmp_path, retention_days=90)

    # Pending markers are recovery signals; startup reconciliation, not
    # ordinary retention, decides whether their transaction was committed.
    assert pending.exists()
    assert not list(tmp_path.glob(f"{base}*"))
