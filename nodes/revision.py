from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import (
    EditorialIssue,
    SectionOutput,
    Task,
)
from schemas.state import State
from services.llm import revision_llm
from prompts.revision import REVISION_SYSTEM


def revision_node(payload: dict) -> dict:
    try:
        task = Task(**payload["task"])

        issues = [EditorialIssue(**issue) for issue in payload["issues"]]

        result = revision_llm.with_structured_output(SectionOutput).invoke(
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

        if result.task_id != task.id:
            raise ValueError(
                f"Revision returned task_id={result.task_id}, expected {task.id}."
            )

        if not result.markdown.strip():
            raise ValueError(f"Revision returned empty Markdown for task {task.id}.")

    except Exception as exc:
        raise RuntimeError(f"Revision failed: {exc}") from exc

    return {"sections": {result.task_id: result}}
