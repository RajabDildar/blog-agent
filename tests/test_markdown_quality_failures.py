import pytest

from services import markdown_quality
from services.markdown_quality import run_markdown_quality_gate


def test_formatter_exception_bubbles_up_as_internal_failure(monkeypatch):
    def broken_formatter(markdown: str) -> str:
        raise RuntimeError("formatter exploded")

    monkeypatch.setattr(
        markdown_quality,
        "format_markdown",
        broken_formatter,
    )

    valid_markdown = """# Blog

## First

Content.
"""

    with pytest.raises(
        RuntimeError,
        match="formatter exploded",
    ):
        run_markdown_quality_gate(
            valid_markdown,
            profile="article",
            expected_title="Blog",
            expected_sections=["First"],
        )
