import time
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from blog_agent.nodes.intent_gateway import (
    blocked_terminal_node,
    cancelled_terminal_node,
    invalid_terminal_node,
    intent_gateway_node,
)
from blog_agent.schemas.models import IntentHumanResponse

from blog_agent.config.settings import (
    CHECKPOINT_SQLITE_PATH,
    MAX_ARTICLE_REPAIRS,
    MAX_EDITORIAL_REVISIONS,
    provider_retry_policy,
)
from blog_agent.nodes.article_validator import (
    article_validator_node,
)
from blog_agent.nodes.citation_verifier import (
    citation_verifier_node,
)
from blog_agent.nodes.editor import editor_node
from blog_agent.nodes.image_generator import generate_images_node
from blog_agent.nodes.image_planner import image_planner_node
from blog_agent.nodes.merger import merge_content
from blog_agent.nodes.orchestrator import orchestrator_node
from blog_agent.nodes.repair import repair_node
from blog_agent.nodes.research import research_node
from blog_agent.nodes.revision import revision_node
from blog_agent.nodes.router import route_next, router_node
from blog_agent.nodes.save import save_node
from blog_agent.nodes.validator import validator_node
from blog_agent.nodes.worker import worker_node
from blog_agent.schemas.context import RunContext
from blog_agent.schemas.state import State
from blog_agent.services.checkpointer import (
    CheckpointerHandle,
    create_checkpointer,
)
from blog_agent.services.rate_limits import (
    RateLimitRetryExhausted,
    get_provider_retry_delay_seconds,
)
from blog_agent.services.run_diagnostics import (
    DiagnosticsSink,
    RunDiagnostics,
    get_current_diagnostics,
    instrument_node,
    load_diagnostics,
)


def fanout(state: State):
    plan = state["plan"]

    if plan is None:
        raise ValueError("Plan missing")

    if not plan.tasks:
        raise ValueError("Plan must contain at least one task.")

    evidence_by_id = {
        evidence.id: evidence
        for evidence in state.get(
            "evidence",
            [],
        )
    }

    sends = []

    for index, task in enumerate(plan.tasks):
        if not task.requires_research:
            if task.evidence_refs:
                raise ValueError(
                    "Task "
                    f"{task.id} does not require research but "
                    f"has evidence_refs: {task.evidence_refs}"
                )

            task_evidence = []
        else:
            seen_refs: set[int] = set()
            task_evidence = []

            for evidence_id in task.evidence_refs:
                if evidence_id in seen_refs:
                    raise ValueError(
                        "Task "
                        f"{task.id} has duplicate evidence reference: "
                        f"{evidence_id}"
                    )

                seen_refs.add(evidence_id)

                evidence = evidence_by_id.get(
                    evidence_id,
                )

                if evidence is None:
                    raise ValueError(
                        f"Task {task.id} references unknown evidence ID: {evidence_id}"
                    )

                task_evidence.append(
                    evidence,
                )

        previous_summary = ""
        next_goal = ""

        if index > 0:
            previous = plan.tasks[index - 1]

            previous_summary = f"{previous.title}: {previous.goal}"

        if index < len(plan.tasks) - 1:
            next_task = plan.tasks[index + 1]

            next_goal = f"{next_task.title}: {next_task.goal}"

        sends.append(
            Send(
                "worker",
                {
                    "task": task.model_dump(),
                    "topic": state["topic"],
                    "mode": state["mode"],
                    "plan": plan.model_dump(),
                    "evidence": [evidence.model_dump() for evidence in task_evidence],
                    "previous_summary": previous_summary,
                    "next_goal": next_goal,
                },
            )
        )

    return sends


def generate_run_id() -> str:
    return uuid4().hex


def _thread_config(
    run_id: str,
) -> dict:
    return {
        "configurable": {
            "thread_id": run_id,
        },
    }


def _thread_exists(
    run_id: str,
) -> bool:
    return (
        _checkpointer_handle.saver.get_tuple(
            _thread_config(run_id),
        )
        is not None
    )


def route_after_citation_verifier(
    state: State,
):
    if state["revision_count"] < MAX_EDITORIAL_REVISIONS:
        return "editor"

    citation_issues = state.get("citation_issues", [])
    if any(issue.severity == "high" for issue in citation_issues):
        return "citation_release_gate_failure"

    return "image_planner"


def route_after_editor(
    state: State,
):
    review = state["editorial_review"]

    if review is None:
        raise ValueError("Editorial review missing.")

    if review.approved:
        return "image_planner"

    issue_map: dict[int, list[dict]] = {}

    for issue in review.issues:
        if issue.task_id is None:
            continue

        issue_map.setdefault(
            issue.task_id,
            [],
        ).append(issue.model_dump())

    if state["plan"] is None:
        raise ValueError("Plan missing during revision routing.")

    requested_ids = [
        task.id
        for task in state["plan"].tasks
        if task.id in review.sections_to_revise and task.id in issue_map
    ]

    if not requested_ids:
        raise ValueError(
            "Editor review approved=False but no actionable section issues remain during routing."
        )

    sends = []

    for task_id in requested_ids:
        section = state["sections"].get(task_id)

        if section is None:
            raise ValueError(f"Missing section {task_id} requested for revision.")

        task = next(
            (task for task in state["plan"].tasks if task.id == task_id),
            None,
        )

        if task is None:
            raise ValueError(f"Unknown task ID {task_id}.")

        evidence_by_id = {
            evidence.id: evidence
            for evidence in state.get(
                "evidence",
                [],
            )
        }

        task_evidence = []

        for evidence_id in task.evidence_refs:
            evidence = evidence_by_id.get(
                evidence_id,
            )

            if evidence is None:
                raise ValueError(
                    f"Task {task.id} references unknown evidence ID: {evidence_id}"
                )

            task_evidence.append(
                evidence,
            )

        sends.append(
            Send(
                "revision",
                {
                    "task": task.model_dump(),
                    "section": section.body_markdown,
                    "issues": issue_map[task_id],
                    "evidence": [evidence.model_dump() for evidence in task_evidence],
                },
            )
        )

    return sends


def route_after_article_validation(
    state: State,
):
    if state["article_validation_passed"]:
        return "citation_verifier"

    if state["article_repair_count"] < MAX_ARTICLE_REPAIRS:
        return "repair"

    return "article_validation_failure"


def route_after_final_validation(
    state: State,
):
    if state["final_validation_passed"]:
        return "save"

    return "final_validation_failure"


def mark_revision(
    state: State,
) -> dict:

    diagnostics = get_current_diagnostics()

    if diagnostics is not None:
        diagnostics.record_revision()

    return {"revision_count": (state["revision_count"] + 1)}


def article_validation_failure_node(
    state: State,
) -> dict:
    errors = state.get(
        "article_validation_errors",
        [],
    )

    raise RuntimeError(
        "Article validation failed after repair:\n"
        + "\n".join(f"- {error}" for error in errors)
    )


def citation_release_gate_failure_node(
    state: State,
) -> dict:
    issues = [
        issue
        for issue in state.get("citation_issues", [])
        if issue.severity == "high"
    ]

    raise RuntimeError(
        "Article publication blocked by citation release gate after maximum editorial revisions:\n"
        + "\n".join(
            f"- Task {issue.task_id if issue.task_id is not None else 'Global'}: {issue.problem}"
            for issue in issues
        )
    )


def final_validation_failure_node(
    state: State,
) -> dict:
    errors = state.get(
        "final_validation_errors",
        [],
    )

    raise RuntimeError(
        "Final artifact validation failed:\n"
        + "\n".join(f"- {error}" for error in errors)
    )


def route_after_intent_gateway(
    state: State,
) -> str:
    status = state.get("intent_status")

    if status == "safe":
        return "router"

    if status == "blocked":
        return "blocked_terminal"

    if status == "invalid":
        return "invalid_terminal"

    if status == "cancelled":
        return "cancelled_terminal"

    return END


# Building graph


def build_graph(
    checkpointer: SqliteSaver,
):
    builder = StateGraph(
        State,
        context_schema=RunContext,
    )

    # ----------------------- Nodes ---------------------------

    builder.add_node(
        "intent_gateway",
        instrument_node(
            "intent_gateway",
            intent_gateway_node,
            provider="gemini+groq",
        ),
    )

    builder.add_node(
        "blocked_terminal",
        instrument_node(
            "blocked_terminal",
            blocked_terminal_node,
        ),
    )

    builder.add_node(
        "invalid_terminal",
        instrument_node(
            "invalid_terminal",
            invalid_terminal_node,
        ),
    )

    builder.add_node(
        "cancelled_terminal",
        instrument_node(
            "cancelled_terminal",
            cancelled_terminal_node,
        ),
    )

    builder.add_node(
        "router",
        instrument_node(
            "router",
            router_node,
            provider="gemini",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "research",
        instrument_node(
            "research",
            research_node,
            provider="tavily+gemini",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "orchestrator",
        instrument_node(
            "orchestrator",
            orchestrator_node,
            provider="gemini",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "worker",
        instrument_node(
            "worker",
            worker_node,
            provider="groq",
        ),
        retry_policy=provider_retry_policy,
    )
    builder.add_node(
        "merge",
        instrument_node(
            "merge",
            merge_content,
        ),
    )

    builder.add_node(
        "citation_verifier",
        instrument_node(
            "citation_verifier",
            citation_verifier_node,
        ),
    )

    builder.add_node(
        "editor",
        instrument_node(
            "editor",
            editor_node,
            provider="gemini",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "revision",
        instrument_node(
            "revision",
            revision_node,
            provider="groq",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "mark_revision",
        instrument_node(
            "mark_revision",
            mark_revision,
        ),
    )

    builder.add_node(
        "article_validator",
        instrument_node(
            "article_validator",
            article_validator_node,
        ),
    )

    builder.add_node(
        "repair",
        instrument_node(
            "repair",
            repair_node,
            provider="groq",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "article_validation_failure",
        instrument_node(
            "article_validation_failure",
            article_validation_failure_node,
        ),
    )

    builder.add_node(
        "citation_release_gate_failure",
        instrument_node(
            "citation_release_gate_failure",
            citation_release_gate_failure_node,
        ),
    )

    builder.add_node(
        "image_planner",
        instrument_node(
            "image_planner",
            image_planner_node,
            provider="gemini",
        ),
        retry_policy=provider_retry_policy,
    )

    builder.add_node(
        "image_generator",
        instrument_node(
            "image_generator",
            generate_images_node,
            provider="cloudflare",
        ),
    )

    builder.add_node(
        "validator",
        instrument_node(
            "validator",
            validator_node,
        ),
    )

    builder.add_node(
        "final_validation_failure",
        instrument_node(
            "final_validation_failure",
            final_validation_failure_node,
        ),
    )

    builder.add_node(
        "save",
        instrument_node(
            "save",
            save_node,
        ),
    )

    # ----------------------- Edges ---------------------------

    builder.add_edge(
        START,
        "intent_gateway",
    )

    builder.add_conditional_edges(
        "intent_gateway",
        route_after_intent_gateway,
        {
            "router": "router",
            "blocked_terminal": "blocked_terminal",
            "invalid_terminal": "invalid_terminal",
            "cancelled_terminal": "cancelled_terminal",
        },
    )

    builder.add_edge(
        "blocked_terminal",
        END,
    )

    builder.add_edge(
        "invalid_terminal",
        END,
    )

    builder.add_edge(
        "cancelled_terminal",
        END,
    )

    builder.add_conditional_edges(
        "router",
        route_next,
        {
            "research": "research",
            "orchestrator": "orchestrator",
        },
    )

    builder.add_edge(
        "research",
        "orchestrator",
    )

    builder.add_conditional_edges(
        "orchestrator",
        fanout,
        ["worker"],
    )

    builder.add_edge(
        "worker",
        "merge",
    )

    builder.add_edge(
        "merge",
        "article_validator",
    )

    builder.add_conditional_edges(
        "article_validator",
        route_after_article_validation,
        {
            "citation_verifier": "citation_verifier",
            "repair": "repair",
            "article_validation_failure": ("article_validation_failure"),
        },
    )

    builder.add_conditional_edges(
        "citation_verifier",
        route_after_citation_verifier,
        {
            "editor": "editor",
            "image_planner": "image_planner",
            "citation_release_gate_failure": "citation_release_gate_failure",
        },
    )

    builder.add_conditional_edges(
        "editor",
        route_after_editor,
    )

    builder.add_edge(
        "revision",
        "mark_revision",
    )

    builder.add_edge(
        "mark_revision",
        "merge",
    )

    builder.add_edge(
        "repair",
        "article_validator",
    )

    builder.add_edge(
        "article_validation_failure",
        END,
    )

    builder.add_edge(
        "citation_release_gate_failure",
        END,
    )

    builder.add_edge(
        "image_planner",
        "image_generator",
    )

    builder.add_edge(
        "image_generator",
        "validator",
    )

    builder.add_conditional_edges(
        "validator",
        route_after_final_validation,
        {
            "save": "save",
            "final_validation_failure": ("final_validation_failure"),
        },
    )

    builder.add_edge(
        "save",
        END,
    )

    builder.add_edge(
        "final_validation_failure",
        END,
    )

    return builder.compile(
        checkpointer=checkpointer,
    )


_checkpointer_handle: CheckpointerHandle = create_checkpointer()

app = build_graph(
    _checkpointer_handle.saver,
)


def _pause_rate_limited_run(
    *,
    run_id: str,
    diagnostics: RunDiagnostics,
    exc: RateLimitRetryExhausted,
) -> None:
    delay = get_provider_retry_delay_seconds(
        exc.rate_limit_info,
    )

    resume_after = time.time() + delay if delay is not None else None

    exc.run_id = run_id
    exc.resume_after = resume_after

    diagnostics.pause_rate_limit(
        info=exc.rate_limit_info,
        resume_after=resume_after,
        exc=exc,
    )


def run(
    user_input: str,
    *,
    run_id: str | None = None,
    diagnostics_sink: DiagnosticsSink | None = None,
    checkpointer_handle: CheckpointerHandle | None = None,
):
    active_handle = checkpointer_handle or _checkpointer_handle
    active_app = (
        build_graph(active_handle.saver)
        if checkpointer_handle is not None
        else app
    )

    if run_id is None:
        run_id = generate_run_id()

    if _thread_exists(run_id):
        raise ValueError(
            f"Run ID already exists: {run_id}. "
            "Use resume(run_id) to continue an existing run."
        )

    diagnostics = RunDiagnostics(
        run_id=run_id,
        original_input=user_input,
        topic="",
        sink=diagnostics_sink,
    )

    context = {
        "diagnostics": diagnostics,
    }

    try:
        result = active_app.invoke(
            {
                "run_id": run_id,
                "original_input": user_input,
                "topic": "",
                "intent_status": "pending",
                "intent_category": "",
                "intent_message": "",
                "clarification_question": "",
                "clarification_options": [],
                "clarification_rounds": 0,
                "clarification_response": "",
                "proposed_topic": "",
                "mode": "",
                "needs_research": False,
                "queries": [],
                "research_focus": [],
                "evidence": [],
                "research_brief": "",
                "plan": None,
                "sections": {},
                "merged_md": "",
                "citation_issues": [],
                "editorial_review": None,
                "revision_count": 0,
                "image_specs": [],
                "image_results": [],
                "final": "",
                "article_validation_errors": [],
                "article_validation_passed": False,
                "article_repair_count": 0,
                "final_validation_errors": [],
                "final_validation_passed": False,
                "saved_path": "",
            },
            {
                "recursion_limit": 50,
                **_thread_config(run_id),
            },
            context=context,
        )

    except RateLimitRetryExhausted as exc:
        _pause_rate_limited_run(
            run_id=run_id,
            diagnostics=diagnostics,
            exc=exc,
        )
        raise

    except Exception as exc:
        diagnostics.finish_failure(exc)
        raise

    current_state = active_app.get_state(_thread_config(run_id))
    current_tasks = getattr(current_state, "tasks", None)
    if current_tasks and getattr(current_tasks[0], "interrupts", None):
        return result

    if result.get("intent_status") in ("blocked", "invalid", "cancelled"):
        return result

    diagnostics.finish_success(result)

    return result


def resume(
    run_id: str,
    *,
    human_response: IntentHumanResponse | None = None,
    diagnostics_sink: DiagnosticsSink | None = None,
    checkpointer_handle: CheckpointerHandle | None = None,
):
    active_handle = checkpointer_handle or _checkpointer_handle
    active_app = (
        build_graph(active_handle.saver)
        if checkpointer_handle is not None
        else app
    )

    config = {
        **_thread_config(run_id),
        "recursion_limit": 50,
    }

    checkpoint = active_handle.saver.get_tuple(
        _thread_config(run_id),
    )

    if checkpoint is None:
        raise ValueError(f"Unknown run ID: {run_id}")

    state = active_app.get_state(
        _thread_config(run_id),
    )

    state_tasks = getattr(state, "tasks", None)
    pending_interrupts = (
        state_tasks[0].interrupts
        if state_tasks and getattr(state_tasks[0], "interrupts", None)
        else ()
    )

    if state.next == () and not pending_interrupts:
        raise ValueError(f"Run {run_id} has already completed successfully.")

    if human_response is not None:
        if not pending_interrupts:
            raise ValueError(f"Run {run_id} has no pending human interrupt.")

        if isinstance(human_response, IntentHumanResponse):
            resume_payload = human_response.model_dump()
        elif isinstance(human_response, dict):
            resume_payload = human_response
        else:
            resume_payload = human_response

        invoke_arg = Command(resume=resume_payload)
    else:
        if pending_interrupts:
            raise ValueError(f"Run {run_id} requires a human response to resume.")
        invoke_arg = None

    diagnostics_data = load_diagnostics(
        run_id,
    )

    if diagnostics_data:
        diagnostics = RunDiagnostics.from_dict(
            diagnostics_data,
            sink=diagnostics_sink,
        )
    else:
        topic = state.values.get(
            "topic",
            "",
        )
        original_input = state.values.get(
            "original_input",
            topic,
        )

        diagnostics = RunDiagnostics(
            run_id=run_id,
            topic=topic,
            original_input=original_input,
            sink=diagnostics_sink,
        )

    if diagnostics.status == "paused_rate_limit":
        resume_after = diagnostics.resume_after

        if resume_after is not None and time.time() < resume_after:
            raise ValueError(
                f"Run {run_id} is paused by provider rate limiting "
                f"until {resume_after:.3f}."
            )

    diagnostics.record_resume()

    context = {
        "diagnostics": diagnostics,
    }

    try:
        result = active_app.invoke(
            invoke_arg,
            config,
            context=context,
            durability="sync",
        )

    except RateLimitRetryExhausted as exc:
        _pause_rate_limited_run(
            run_id=run_id,
            diagnostics=diagnostics,
            exc=exc,
        )
        raise

    except Exception as exc:
        diagnostics.finish_failure(
            exc,
        )
        raise

    current_state = active_app.get_state(_thread_config(run_id))
    current_tasks = getattr(current_state, "tasks", None)
    if current_tasks and getattr(current_tasks[0], "interrupts", None):
        return result

    if result.get("intent_status") in ("blocked", "invalid", "cancelled"):
        return result

    diagnostics.finish_success(
        result,
    )

    return result

