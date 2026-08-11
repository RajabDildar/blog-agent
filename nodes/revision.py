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

    return {"sections": {result.task_id: result}}
