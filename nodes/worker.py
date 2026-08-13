from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import (
    Plan,
    ResearchEvidence,
    SectionOutput,
    Task,
)
from services.llm import writer_llm
from prompts.writer import WORKER_SYSTEM
from services.section_validation import (
    validate_section_markdown,
)


def worker_node(payload: dict) -> dict:
    try:
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
            SectionOutput, method="json_mode"
        ).invoke(
            [
                SystemMessage(content=WORKER_SYSTEM),
                HumanMessage(
                    content=(
                        f"Topic: {payload['topic']}\n"
                        f"Mode: {payload['mode']}\n\n"
                        f"Thesis:\n{plan.thesis}\n\n"
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

        if result.task_id != task.id:
            raise ValueError(
                f"Worker returned task_id={result.task_id}, expected {task.id}."
            )

        if not result.markdown.strip():
            raise ValueError(f"Worker returned empty Markdown for task {task.id}.")

        section_errors = validate_section_markdown(
            result.markdown,
            expected_title=task.title,
        )

        if section_errors:
            raise ValueError(
                f"Worker produced invalid section "
                f"{task.id}:\n" + "\n".join(f"- {error}" for error in section_errors)
            )

    except Exception as exc:
        raise RuntimeError(f"Worker failed: {exc}") from exc

    return {"sections": {result.task_id: result}}
