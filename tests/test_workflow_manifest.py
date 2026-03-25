import json
import re
from datetime import datetime, timezone
from pathlib import Path


def test_generate_run_id_is_path_safe():
    from src.workflow.manifest import generate_run_id

    run_id = generate_run_id()
    assert " " not in run_id
    assert "/" not in run_id
    assert re.match(r"^\d{8}T\d{6}Z-[a-z0-9]{8}$", run_id)


def test_generate_run_id_avoids_collision_with_same_second():
    from src.workflow.manifest import generate_run_id

    now = datetime(2026, 3, 25, 1, 2, 3, tzinfo=timezone.utc)
    first = generate_run_id(now=now)
    second = generate_run_id(now=now)

    assert first != second
    assert first.startswith("20260325T010203Z-")
    assert second.startswith("20260325T010203Z-")


def test_write_workflow_manifest_writes_per_run_and_latest_copy(tmp_path):
    from src.workflow.manifest import write_workflow_manifest

    payload = {
        "run_id": "20260325T010203Z-abcd1234",
        "started_at": "2026-03-25T01:02:03Z",
        "finished_at": "2026-03-25T01:02:05Z",
        "status": "succeeded",
        "exit_code": 0,
        "preflight_result": {"status": "passed", "checks": [], "failed_checks": []},
    }
    paths = write_workflow_manifest(payload, root=tmp_path / "reports" / "workflow")

    assert paths["manifest_path"].endswith("runs/20260325T010203Z-abcd1234/workflow_manifest.json")
    assert (tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json").exists()
    manifest_payload = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))
    latest_payload = json.loads(
        (tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json").read_text(encoding="utf-8")
    )
    assert manifest_payload["started_at"] == "2026-03-25T01:02:03Z"
    assert manifest_payload["preflight_result"]["status"] == "passed"
    assert latest_payload == manifest_payload
