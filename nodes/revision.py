from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import EditorialIssue, SectionOutput, Task
from services.llm import revision_llm
from prompts.revision import REVISION_SYSTEM

from services.markdown_llm_repair import (
    repair_markdown_with_llm,
)
from services.markdown_quality import (
    run_markdown_quality_gate,
)


def revision_node(payload: dict) -> dict:
    try:
        task = Task(**payload["task"])

        issues = [EditorialIssue(**issue) for issue in payload["issues"]]

        result = revision_llm.with_structured_output(
            SectionOutput,
            method="json_mode",
        ).invoke(
            [
                SystemMessage(content=REVISION_SYSTEM),
                HumanMessage(
                    content=(
                        f"Section:\n{payload['section']}\n\n"
                        f"Task:\n{task.model_dump()}\n\n"
                        f"Editor issues:\n"
                        f"{[i.model_dump() for i in issues]}"
                    )
                ),
            ]
        )

        markdown = result.body_markdown.strip()

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
        )

        if gate.errors:
            raise ValueError(
                f"Revision produced invalid "
                f"section {task.id}:\n"
                + "\n".join(f"- {error}" for error in gate.errors)
            )

        section = SectionOutput(
            body_markdown=gate.markdown,
        )

    except Exception as exc:
        raise RuntimeError(f"Revision failed: {exc}") from exc

    return {
        "sections": {
            task.id: section,
        }
    }
