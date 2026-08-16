import json

import pytest

import main
from services.run_diagnostics import (
    format_cli_summary,
    load_diagnostics,
)

RUN_ID = "f" * 32


def write_diagnostics(tmp_path, payload):
    path = tmp_path / "runs" / RUN_ID / "diagnostics.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_diagnostics_reads_run_specific_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    payload = {
        "run_id": RUN_ID,
        "topic": "Test topic",
        "status": "failed",
        "current_stage": "worker",
        "current_provider": "groq",
        "retry_count": 3,
        "provider_attempts": {"groq": 4},
        "failure": {
            "node": "worker",
            "provider": "groq",
            "attempt": 4,
            "exception_type": "RateLimitError",
            "message": "rate limited",
        },
    }

    write_diagnostics(tmp_path, payload)

    assert load_diagnostics(RUN_ID) == payload


def test_format_cli_summary_includes_failure_context():
    payload = {
        "run_id": RUN_ID,
        "topic": "Test topic",
        "status": "failed",
        "current_stage": "worker",
        "current_provider": "groq",
        "retry_count": 3,
        "provider_attempts": {"groq": 4},
        "failure": {
            "node": "worker",
            "provider": "groq",
            "attempt": 4,
            "exception_type": "RateLimitError",
            "message": "rate limited",
        },
    }

    summary = format_cli_summary(payload)

    assert f"Run ID: {RUN_ID}" in summary
    assert "Stage: worker" in summary
    assert "Provider: groq" in summary
    assert "Attempts: 4" in summary
    assert "Retries: 3" in summary
    assert "Failure: RateLimitError" in summary
    assert "rate limited" in summary
    assert "Diagnostics: runs/" in summary


def test_main_reports_failure_without_wrapping_exception(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "test topic")

    def fake_run(topic, *, run_id):
        assert topic == "test topic"
        assert run_id == RUN_ID

        payload = {
            "run_id": RUN_ID,
            "topic": topic,
            "status": "failed",
            "current_stage": "editor",
            "current_provider": "gemini",
            "retry_count": 1,
            "provider_attempts": {"gemini": 2},
            "failure": {
                "node": "editor",
                "provider": "gemini",
                "attempt": 2,
                "exception_type": "ServerError",
                "message": "temporary failure",
            },
        }

        write_diagnostics(tmp_path, payload)
        raise RuntimeError("temporary failure")

    monkeypatch.setattr(main, "run", fake_run)
    monkeypatch.setattr(main, "generate_run_id", lambda: RUN_ID)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    output = capsys.readouterr().out

    assert f"Run ID: {RUN_ID}" in output
    assert "Stage: editor" in output
    assert "Provider: gemini" in output
    assert "Attempts: 2" in output
    assert "Failure: ServerError" in output
    assert "Diagnostics:" in output
