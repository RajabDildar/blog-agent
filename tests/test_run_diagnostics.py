import json
from pathlib import Path
from types import SimpleNamespace

from services.run_diagnostics import (
    RunDiagnostics,
    instrument_node,
)


class FakeRuntime:
    def __init__(self, diagnostics, node_attempt=1):
        self.context = {"diagnostics": diagnostics}
        self.execution_info = SimpleNamespace(
            node_attempt=node_attempt,
            run_id=None,
            thread_id=None,
            checkpoint_id="checkpoint",
            checkpoint_ns="",
            task_id="task",
        )


def test_diagnostics_records_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    diagnostics = RunDiagnostics(
        run_id="a" * 32,
        topic="HTTP lifecycle",
    )

    wrapped = instrument_node(
        "router",
        lambda state: {"ok": True},
        provider="gemini",
    )

    result = wrapped({}, FakeRuntime(diagnostics))
    diagnostics.finish_success(result)

    data = json.loads(
        Path("runs", "a" * 32, "diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    assert result == {"ok": True}
    assert data["status"] == "success"
    assert data["current_stage"] == "router"
    assert data["provider_attempts"]["gemini"] == 1
    assert any(
        event["event"] == "node_succeeded"
        and event["node"] == "router"
        for event in data["events"]
    )


def test_diagnostics_records_retry_attempt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    diagnostics = RunDiagnostics(
        run_id="b" * 32,
        topic="Retry test",
    )

    attempts = 0

    def failing_node(state):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("provider exhausted")

    wrapped = instrument_node(
        "worker",
        failing_node,
        provider="groq",
    )

    for attempt in (1, 2, 3):
        try:
            wrapped({}, FakeRuntime(diagnostics, node_attempt=attempt))
        except RuntimeError:
            pass

    diagnostics.finish_failure(RuntimeError("provider exhausted"))

    data = json.loads(
        Path("runs", "b" * 32, "diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    assert attempts == 3
    assert data["retry_count"] == 2
    assert data["provider_attempts"]["groq"] == 3
    assert data["current_stage"] == "worker"
    assert data["failure"]["node"] == "worker"
    assert data["failure"]["exception_type"] == "RuntimeError"
    assert data["failure"]["message"] == "provider exhausted"


def test_diagnostics_records_domain_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    diagnostics = RunDiagnostics(
        run_id="c" * 32,
        topic="Metrics",
    )

    diagnostics.record_markdown_gate(
        deterministic_repair_applied=True,
        llm_repair_applied=True,
    )
    diagnostics.record_markdown_gate(
        deterministic_repair_applied=True,
        llm_repair_applied=False,
    )

    diagnostics.record_editorial_review()
    diagnostics.record_revision()
    diagnostics.record_image_attempt("img-1")
    diagnostics.record_image_attempt("img-2")
    diagnostics.record_final_validation(
        ["missing image", "duplicate image"]
    )

    diagnostics.finish_success(
        {
            "revision_count": 1,
            "article_repair_count": 1,
            "image_results": [
                {"id": "img-1", "status": "inserted"},
                {"id": "img-2", "status": "inserted"},
            ],
            "final_validation_errors": [],
        }
    )

    data = json.loads(
        Path("runs", "c" * 32, "diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    assert data["markdown"]["deterministic_repairs"] == 2
    assert data["markdown"]["llm_repairs"] == 1
    assert data["editorial_reviews"] == 1
    assert data["editorial_revisions"] == 1
    assert data["image_attempts"] == 2
    assert data["final_validation_failures"] == 2


def test_diagnostics_are_isolated_by_run_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    first = RunDiagnostics(
        run_id="d" * 32,
        topic="Same topic",
    )
    second = RunDiagnostics(
        run_id="e" * 32,
        topic="Same topic",
    )

    first.finish_success({})
    second.finish_success({})

    assert Path(
        "runs", "d" * 32, "diagnostics.json"
    ).is_file()

    assert Path(
        "runs", "e" * 32, "diagnostics.json"
    ).is_file()
