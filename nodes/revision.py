from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import EditorialIssue, SectionOutput, Task, MarkdownRepairOutput
from schemas.state import State
from services.llm import revision_llm
from prompts.revision import REVISION_SYSTEM
from services.section_validation import (
    validate_section_markdown,
)
from prompts.writer_repair import WRITER_REPAIR_SYSTEM


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
    repairer = revision_llm.with_structured_output(MarkdownRepairOutput)

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
        raise ValueError(f"Revision repair returned empty Markdown for task {task.id}.")

    return result.markdown


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

        markdown = result.markdown.strip()

        if not markdown:
            raise ValueError(f"Revision returned empty Markdown for task {task.id}.")

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
                    f"Revision produced invalid section {task.id} "
                    f"after repair:\n" + "\n".join(f"- {error}" for error in errors)
                )

        section = SectionOutput(
            markdown=markdown,
        )

    except Exception as exc:
        raise RuntimeError(f"Revision failed: {exc}") from exc

    return {
        "sections": {
            task.id: section,
        }
    }
