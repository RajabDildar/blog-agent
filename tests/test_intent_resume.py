from unittest.mock import MagicMock, patch
import pytest

from blog_agent.graph import main_graph
from blog_agent.schemas.models import IntentAnalysis, IntentHumanResponse
from blog_agent.services.checkpointer import create_checkpointer
from blog_agent.services.run_diagnostics import RunDiagnostics, load_diagnostics


def test_resume_rejects_human_response_when_no_interrupt_pending(tmp_path):
    handle = create_checkpointer(tmp_path / "checkpoints.sqlite")
    original_handle = main_graph._checkpointer_handle
    main_graph._checkpointer_handle = handle

    try:
        run_id = "test-no-interrupt-resume"
        # Seed a run that failed during ordinary execution without interrupt
        config = {"configurable": {"thread_id": run_id}}
        diagnostics = RunDiagnostics(run_id=run_id, topic="Test")

        # Mock app that has next node but no interrupt
        mock_app = MagicMock()
        mock_state = MagicMock()
        mock_state.next = ("worker",)
        mock_state.tasks = []
        mock_app.get_state.return_value = mock_state

        original_app = main_graph.app
        main_graph.app = mock_app

        # Mock checkpointer returning a tuple
        handle.saver.get_tuple = MagicMock(return_value=({"some": "checkpoint"},))

        try:
            with pytest.raises(
                ValueError,
                match=f"Run {run_id} has no pending human interrupt.",
            ):
                main_graph.resume(
                    run_id,
                    human_response=IntentHumanResponse(action="proceed"),
                )
        finally:
            main_graph.app = original_app

    finally:
        main_graph._checkpointer_handle = original_handle
        handle.close()


def test_resume_rejects_missing_human_response_when_interrupt_pending(tmp_path):
    handle = create_checkpointer(tmp_path / "checkpoints.sqlite")
    original_handle = main_graph._checkpointer_handle
    main_graph._checkpointer_handle = handle

    try:
        run_id = "test-pending-interrupt-no-response"
        mock_app = MagicMock()
        mock_state = MagicMock()
        mock_state.next = ("intent_gateway",)
        mock_task = MagicMock()
        mock_task.interrupts = [MagicMock(value={"type": "clarification_required"})]
        mock_state.tasks = [mock_task]
        mock_app.get_state.return_value = mock_state

        original_app = main_graph.app
        main_graph.app = mock_app
        handle.saver.get_tuple = MagicMock(return_value=({"some": "checkpoint"},))

        try:
            with pytest.raises(
                ValueError,
                match=f"Run {run_id} requires a human response to resume.",
            ):
                main_graph.resume(run_id)
        finally:
            main_graph.app = original_app

    finally:
        main_graph._checkpointer_handle = original_handle
        handle.close()


def test_resume_with_human_response_invokes_command_resume(tmp_path):
    handle = create_checkpointer(tmp_path / "checkpoints.sqlite")
    original_handle = main_graph._checkpointer_handle
    main_graph._checkpointer_handle = handle

    try:
        run_id = "test-successful-interrupt-resume"
        mock_app = MagicMock()

        # State 1: has pending interrupt
        mock_state = MagicMock()
        mock_state.next = ("intent_gateway",)
        mock_task = MagicMock()
        mock_task.interrupts = [MagicMock(value={"type": "clarification_required"})]
        mock_state.tasks = [mock_task]
        mock_state.values = {"topic": "", "original_input": "AI"}

        # State 2 (after invoke): finished
        mock_state_after = MagicMock()
        mock_state_after.tasks = []
        mock_state_after.next = ()

        mock_app.get_state.side_effect = [mock_state, mock_state_after]
        mock_app.invoke.return_value = {
            "intent_status": "safe",
            "topic": "Autonomous AI Agents in Production",
        }

        original_app = main_graph.app
        main_graph.app = mock_app
        handle.saver.get_tuple = MagicMock(return_value=({"some": "checkpoint"},))

        try:
            resp = IntentHumanResponse(
                action="select_option",
                value="Autonomous AI Agents in Production",
            )
            result = main_graph.resume(
                run_id,
                human_response=resp,
            )

            assert result["intent_status"] == "safe"
            assert result["topic"] == "Autonomous AI Agents in Production"
            assert mock_app.invoke.called
            # Verify command was used
            invoked_arg = mock_app.invoke.call_args[0][0]
            assert hasattr(invoked_arg, "resume")
            assert invoked_arg.resume["value"] == "Autonomous AI Agents in Production"
        finally:
            main_graph.app = original_app

    finally:
        main_graph._checkpointer_handle = original_handle
        handle.close()
