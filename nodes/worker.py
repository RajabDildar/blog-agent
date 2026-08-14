from langchain_core.messages import HumanMessage, SystemMessage

from prompts.writer_repair import WRITER_REPAIR_SYSTEM
from prompts.writer import WORKER_SYSTEM
from schemas.models import (
    MarkdownRepairOutput,
    Plan,
    ResearchEvidence,
    SectionOutput,
    Task,
)
from services.llm import writer_llm
from services.section_validation import validate_section_markdown


def _validate_section(
    markdown: str,
    *,
    task: Task,
) -> list[str]:
    return validate_section_markdown(
        markdown,
        expected_title=task.title,
    )


def _repair_section(
    *,
    task: Task,
    markdown: str,
    errors: list[str],
) -> str:
    repairer = writer_llm.with_structured_output(MarkdownRepairOutput)

    result = repairer.invoke(
        [
            SystemMessage(content=WRITER_REPAIR_SYSTEM),
            HumanMessage(
                content=(
                    f"Task title:\n"
                    f"{task.title}\n\n"
                    f"Task goal:\n"
                    f"{task.goal}\n\n"
                    f"Validation errors:\n"
                    f"{errors}\n\n"
                    f"Current Markdown:\n"
                    f"{markdown}"
                )
            ),
        ]
    )

    if not result.markdown.strip():
        raise ValueError(f"Worker repair returned empty Markdown for task {task.id}.")

    return result.markdown


def worker_node(payload: dict) -> dict:
    task = Task(**payload["task"])
    plan = Plan(**payload["plan"])

    evidence = [ResearchEvidence(**e) for e in payload.get("evidence", [])]

    evidence_text = "\n".join(
        (
            f"- Claim: {e.claim}\n"
            f"  Source: {e.source_title}\n"
            f"  URL: {e.url}\n"
            f"  Evidence: {e.supporting_text}"
        )
        for e in evidence[:12]
    )

    previous_summary = payload.get(
        "previous_summary",
        "",
    )

    next_goal = payload.get(
        "next_goal",
        "",
    )

    result = writer_llm.with_structured_output(
        SectionOutput,
        method="json_mode",
    ).invoke(
        [
            SystemMessage(content=WORKER_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {payload['topic']}\n"
                    f"Mode: {payload['mode']}\n\n"
                    f"Thesis:\n"
                    f"{plan.thesis}\n\n"
                    f"Reader promise:\n"
                    f"{plan.reader_promise}\n\n"
                    f"Full outline:\n"
                    f"{[t.model_dump() for t in plan.tasks]}\n\n"
                    f"Previous section summary:\n"
                    f"{previous_summary}\n\n"
                    f"Next section goal:\n"
                    f"{next_goal}\n\n"
                    f"Current section:\n"
                    f"{task.model_dump()}\n\n"
                    f"Evidence:\n"
                    f"{evidence_text}"
                )
            ),
        ]
    )

    markdown = result.markdown.strip()

    if not markdown:
        raise ValueError(f"Worker returned empty Markdown for task {task.id}.")

    # First validation.
    errors = _validate_section(
        markdown,
        task=task,
    )

    # One section-level recovery attempt.
    if errors:
        markdown = _repair_section(
            task=task,
            markdown=markdown,
            errors=errors,
        ).strip()

        # Validate repaired output again.
        errors = _validate_section(
            markdown,
            task=task,
        )

        if errors:
            raise ValueError(
                f"Worker produced invalid section {task.id} "
                f"after repair:\n" + "\n".join(f"- {error}" for error in errors)
            )

    section = SectionOutput(
        markdown=markdown,
    )

    return {
        "sections": {
            task.id: section,
        }
    }
