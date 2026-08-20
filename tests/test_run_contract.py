from graph.main_graph import _thread_exists, _thread_config, generate_run_id
import graph.main_graph as main_graph


def test_generate_run_id_is_non_empty():
    run_id = generate_run_id()

    assert run_id
    assert isinstance(run_id, str)


def test_thread_config_uses_run_id():
    run_id = "run-contract-test"

    assert _thread_config(run_id) == {
        "configurable": {
            "thread_id": run_id,
        },
    }


def test_unknown_thread_does_not_exist():
    run_id = "unknown-run-contract-test"

    assert _thread_exists(run_id) is False


def test_run_rejects_existing_thread(
    monkeypatch,
):
    run_id = "existing-run-contract-test"

    monkeypatch.setattr(
        main_graph,
        "_thread_exists",
        lambda value: value == run_id,
    )

    try:
        main_graph.run(
            "test topic",
            run_id=run_id,
        )
    except ValueError as exc:
        assert str(exc) == (
            f"Run ID already exists: {run_id}. "
            "Use resume(run_id) to continue an existing run."
        )
    else:
        raise AssertionError("run() did not reject an existing run ID")
