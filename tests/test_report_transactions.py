import importlib.util
import sys
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
