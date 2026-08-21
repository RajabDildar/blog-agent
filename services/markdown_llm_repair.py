from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from config.settings import (
    groq_admission_controller,
)
from prompts.repair import REPAIR_SYSTEM
from schemas.models import (
    MarkdownRepairOutput,
)
from services.groq_admission import (
    invoke_with_groq_admission,
)

RepairScope = Literal[
    "section",
    "article",
]


def repair_markdown_with_llm(
    *,
    llm,
    markdown: str,
    errors: list[str],
    scope: RepairScope,
    expected_title: str,
    expected_sections: Sequence[str] = (),
) -> str:
    repairer = llm.with_structured_output(MarkdownRepairOutput)

    result = invoke_with_groq_admission(
        controller=groq_admission_controller,
        runnable=repairer,
        input=[
            SystemMessage(content=REPAIR_SYSTEM),
            HumanMessage(
                content=(
                    f"Scope: {scope}\n\n"
                    f"Expected title:\n"
                    f"{expected_title}\n\n"
                    f"Expected H2 sections:\n"
                    f"{list(expected_sections)}"
                    f"\n\n"
                    f"Validation errors:\n"
                    + "\n".join(f"- {error}" for error in errors)
                    + "\n\n"
                    f"Current Markdown:\n"
                    f"{markdown}"
                )
            ),
        ],
    )

    repaired = result.markdown.strip()

    if not repaired:
        raise ValueError("Markdown repair returned empty Markdown.")

    return repaired
