import re

from schemas.state import State


def validate_markdown(markdown: str) -> list[str]:
    errors: list[str] = []

    if not markdown.startswith("# "):
        errors.append("Missing H1 title.")

    if "[[IMAGE_" in markdown:
        errors.append("Unresolved image placeholder.")

    if "IMAGE GENERATION FAILED" in markdown:
        errors.append("Image failure text leaked into output.")

    if "Not found in provided sources." in markdown:
        errors.append("Unsupported claim marker leaked into output.")

    fenced_blocks = re.findall(
        r"```",
        markdown,
    )

    if len(fenced_blocks) % 2 != 0:
        errors.append("Unclosed Markdown code fence.")

    return errors


def validator_node(state: State) -> dict:
    errors = validate_markdown(state["final"])

    if errors:
        raise ValueError(
            "Final Markdown validation failed:\n"
            + "\n".join(f"- {error}" for error in errors)
        )

    return {}
