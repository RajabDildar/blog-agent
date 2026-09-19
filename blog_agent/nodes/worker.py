from langchain_core.messages import HumanMessage, SystemMessage

from blog_agent.config.settings import (
    groq_admission_controller,
)
from blog_agent.prompts.writer import WORKER_SYSTEM
from blog_agent.schemas.models import (
    Plan,
    ResearchEvidence,
    SectionOutput,
    Task,
)
from blog_agent.services.groq_admission import (
    invoke_with_groq_admission,
)
from blog_agent.services.llm import writer_llm
from blog_agent.services.markdown_llm_repair import (
    repair_markdown_with_llm,
)
from blog_agent.services.markdown_quality import (
    run_markdown_quality_gate,
)
from blog_agent.services.run_diagnostics import (
    get_current_diagnostics,
)


def _citation_requirement_block(
    task: Task,
    evidence: list[ResearchEvidence],
) -> str:
    """Return a plain-text Citation Requirements block for the worker prompt."""
    if not task.requires_citations:
        return (
            "CITATION REQUIREMENTS:\n"
            "- requires_citations is FALSE for this section.\n"
            "- Do NOT add external citation links.\n"
        )

    url_lines = "\n".join(
        f"  * {e.url}  ({e.source_title})"
        for e in evidence
        if e.url
    ) or "  (no evidence assigned)"

    return (
        "CITATION REQUIREMENTS (MANDATORY):\n"
        "- requires_citations is TRUE for this section.\n"
        "- You MUST include at least one inline Markdown citation link in the body.\n"
        "- ONLY format accepted:  [Anchor Text](URL)\n"
        "- Example: According to [Report Title](https://example.com), X grew by 40%.\n"
        "- Allowed URLs for this section:\n"
        f"{url_lines}\n"
        "- DO NOT use raw URLs, bracketed URLs (【url】), or footnotes ([^1]).\n"
        "- DO NOT write text-only attributions like '(source: Report, 2026)'.\n"
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
            f"  Source type: {e.source_type}\n"
            f"  Authority score: {e.authority_score}\n"
            f"  Support strength: {e.support_strength}\n"
            f"  Confidence score: {e.confidence_score}\n"
            f"  Evidence: {e.supporting_text}"
        )
        for e in evidence
    )

    previous_summary = payload.get(
        "previous_summary",
        "",
    )

    next_goal = payload.get(
        "next_goal",
        "",
    )

    writer = writer_llm.with_structured_output(
        SectionOutput,
        method="json_mode",
    )

    result = invoke_with_groq_admission(
        controller=groq_admission_controller,
        runnable=writer,
        input=[
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
                    f"{evidence_text}\n\n"
                    + _citation_requirement_block(task, evidence)
                )
            ),
        ],
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
        ),
            diagnostics=diagnostics,
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
