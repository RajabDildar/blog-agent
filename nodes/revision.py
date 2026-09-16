from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from config.settings import (
    groq_admission_controller,
)
from prompts.revision import REVISION_SYSTEM
from schemas.models import (
    EditorialIssue,
    ResearchEvidence,
    SectionOutput,
    Task,
)
from services.groq_admission import (
    invoke_with_groq_admission,
)
from services.llm import revision_llm
from services.markdown_llm_repair import (
    repair_markdown_with_llm,
)
from services.markdown_quality import (
    run_markdown_quality_gate,
)
from services.run_diagnostics import (
    get_current_diagnostics,
)


def _revision_citation_block(
    task: Task,
    evidence: list[ResearchEvidence],
) -> str:
    """Return a plain-text Citation Requirements block for the revision prompt."""
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
        "- You MUST add inline Markdown citation links to fix missing-citation issues.\n"
        "- ONLY format accepted:  [Anchor Text](URL)\n"
        "- Example: According to [Report Title](https://example.com), X grew by 40%.\n"
        "- Allowed URLs for this section:\n"
        f"{url_lines}\n"
        "- DO NOT use raw URLs, bracketed URLs (\u3010url\u3011), or footnotes ([^1]).\n"
        "- DO NOT write text-only attributions like '(source: Report, 2026)'.\n"
    )


def revision_node(
    payload: dict,
) -> dict:
    task = Task(**payload["task"])

    issues = [EditorialIssue(**issue) for issue in payload["issues"]]

    evidence = [
        ResearchEvidence(**item)
        for item in payload.get(
            "evidence",
            [],
        )
    ]

    reviser = revision_llm.with_structured_output(
        SectionOutput,
        method="json_mode",
    )

    evidence_text = "\n".join(
        (
            f"- Claim: {e.claim}\n"
            f"  Source: {e.source_title}\n"
            f"  URL: {e.url}\n"
            f"  Support strength: {e.support_strength}\n"
            f"  Evidence: {e.supporting_text}"
        )
        for e in evidence
    )

    result = invoke_with_groq_admission(
        controller=groq_admission_controller,
        runnable=reviser,
        input=[
            SystemMessage(content=REVISION_SYSTEM),
            HumanMessage(
                content=(
                    f"Section:\n"
                    f"{payload['section']}\n\n"
                    f"Task:\n"
                    f"{task.model_dump()}\n\n"
                    f"Editor issues:\n"
                    f"{[i.model_dump() for i in issues]}\n\n"
                    f"Assigned evidence:\n"
                    f"{evidence_text}\n\n"
                    + _revision_citation_block(task, evidence)
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
            llm=revision_llm,
            markdown=current,
            errors=errors,
            scope="section",
            expected_title=task.title,
        ),
            diagnostics=diagnostics,
    )

    if gate.errors:
        raise ValueError(
            f"Revision produced invalid "
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
