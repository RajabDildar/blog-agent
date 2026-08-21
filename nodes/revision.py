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


def revision_node(
    payload: dict,
) -> dict:
    task = Task(**payload["task"])

    issues = [EditorialIssue(**issue) for issue in payload["issues"]]

    reviser = revision_llm.with_structured_output(
        SectionOutput,
        method="json_mode",
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
                    f"{[i.model_dump() for i in issues]}"
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
            diagnostics=diagnostics,
        ),
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
