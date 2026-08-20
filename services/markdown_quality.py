from collections.abc import (
    Callable,
    Sequence,
)
from dataclasses import dataclass
from typing import Literal

from services.markdown_format import (
    format_markdown,
    normalize_markdown,
)
from services.markdown_repair import (
    repair_article_structure,
    repair_section_structure,
)
from services.markdown_validation import (
    validate_article_markdown,
)
from services.run_diagnostics import (
    RunDiagnostics,
)
from services.section_validation import (
    validate_section_markdown,
)

Profile = Literal[
    "section",
    "article",
]

RepairCallback = Callable[
    [str, list[str]],
    str,
]


@dataclass(
    frozen=True,
    slots=True,
)
class MarkdownGateResult:
    markdown: str
    errors: list[str]
    deterministic_repair_applied: bool = False
    llm_repair_applied: bool = False


def _validate(
    markdown: str,
    *,
    profile: Profile,
    expected_title: str,
    expected_sections: Sequence[str],
) -> list[str]:
    if profile == "section":
        return validate_section_markdown(markdown)

    return validate_article_markdown(
        markdown,
        expected_title=expected_title,
        expected_sections=expected_sections,
    )


def _deterministic_repair(
    markdown: str,
    *,
    profile: Profile,
    expected_title: str,
) -> str:
    if profile == "section":
        return repair_section_structure(
            markdown,
            expected_title=expected_title,
        )

    return repair_article_structure(markdown)


def run_markdown_quality_gate(
    markdown: str,
    *,
    profile: Profile,
    expected_title: str,
    expected_sections: Sequence[str] = (),
    llm_repair: RepairCallback | None = None,
    diagnostics: RunDiagnostics | None = None,
) -> MarkdownGateResult:
    current = normalize_markdown(markdown)

    errors = _validate(
        current,
        profile=profile,
        expected_title=expected_title,
        expected_sections=expected_sections,
    )

    deterministic_applied = False
    llm_applied = False

    # 1. Deterministic repair
    if errors:
        repaired = _deterministic_repair(
            current,
            profile=profile,
            expected_title=expected_title,
        )

        if repaired != current:
            current = repaired
            deterministic_applied = True

            errors = _validate(
                current,
                profile=profile,
                expected_title=expected_title,
                expected_sections=(expected_sections),
            )

    # 2. LLM repair
    if errors and llm_repair is not None:
        current = normalize_markdown(
            llm_repair(
                current,
                errors,
            )
        )

        llm_applied = True

        errors = _validate(
            current,
            profile=profile,
            expected_title=expected_title,
            expected_sections=(expected_sections),
        )

    # Still invalid: do not format it.
    if errors:
        if diagnostics is not None:
            diagnostics.record_markdown_gate(
                deterministic_repair_applied=(deterministic_applied),
                llm_repair_applied=(llm_applied),
            )

        return MarkdownGateResult(
            markdown=current,
            errors=errors,
            deterministic_repair_applied=(deterministic_applied),
            llm_repair_applied=llm_applied,
        )

    # 3. Canonical formatting
    formatted = format_markdown(current)

    # 4. Never trust a transformation blindly.
    final_errors = _validate(
        formatted,
        profile=profile,
        expected_title=expected_title,
        expected_sections=expected_sections,
    )

    if diagnostics is not None:
        diagnostics.record_markdown_gate(
            deterministic_repair_applied=(deterministic_applied),
            llm_repair_applied=(llm_applied),
        )

    return MarkdownGateResult(
        markdown=formatted,
        errors=final_errors,
        deterministic_repair_applied=(deterministic_applied),
        llm_repair_applied=llm_applied,
    )
