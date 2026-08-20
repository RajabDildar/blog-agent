from langchain_core.messages import HumanMessage, SystemMessage

from prompts.writer import WORKER_SYSTEM
from schemas.models import (
    Plan,
    ResearchEvidence,
    SectionOutput,
    Task,
)
from services.llm import writer_llm
from services.markdown_llm_repair import (
    repair_markdown_with_llm,
)
from services.markdown_quality import (
    run_markdown_quality_gate,
)
from services.run_diagnostics import (
    get_current_diagnostics,
)


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

    markdown = result.body_markdown.strip()

    diagnostics = get_current_diagnostics()

    gate = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title=task.title,
        llm_repair=lambda current, errors: repair_markdown_with_llm(
            llm=writer_llm,
            markdown=current,
            errors=errors,
            scope="section",
            expected_title=task.title,
            diagnostics=diagnostics,
        ),
    )

    if gate.errors:
        raise ValueError(
            f"Worker produced invalid "
            f"section {task.id}:\n" + "\n".join(f"- {error}" for error in gate.errors)
        )

    section = SectionOutput(
        body_markdown=gate.markdown,
    )

    return {
        "sections": {
            task.id: section,
        }
    }
