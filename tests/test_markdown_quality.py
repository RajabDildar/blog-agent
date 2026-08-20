from services import markdown_quality
from services.markdown_quality import (
    run_markdown_quality_gate,
)


def test_section_gate_removes_duplicated_h2():
    markdown = """## HTTP Headers

Content.
### Header Example

More content.
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="HTTP Headers",
    )

    assert result.errors == []
    assert "## HTTP Headers" not in result.markdown
    assert "### Header Example" in result.markdown
    assert result.deterministic_repair_applied
    assert result.llm_repair_applied is False


def test_section_gate_demotes_unexpected_h2():
    markdown = """Intro.
## Nested Idea

Details.
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="HTTP",
    )

    assert result.errors == []
    assert "### Nested Idea" in result.markdown


def test_article_gate_preserves_h3_and_table():
    markdown = """# HTTP

## Request
### Headers

| Name | Meaning |
| --- | --- |
| Host | Target host |
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="article",
        expected_title="HTTP",
        expected_sections=[
            "Request",
        ],
    )

    assert result.errors == []
    assert "### Headers" in result.markdown
    assert "| Name" in result.markdown


def test_complex_section_markdown_survives_quality_gate():
    markdown = """Intro paragraph.

### Detection Pipeline

| Stage | Purpose |
| --- | --- |
| Score | Estimate risk |

```python
# Python comment, not an H1.
## Python comment, not an H2.
score = model.predict(features)
```

> Review high-risk results before taking action.

- Signals
  - device
  - velocity

See the [reference](https://example.com/reference).
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="Fraud Detection",
    )

    assert result.errors == []
    assert "### Detection Pipeline" in result.markdown
    assert "| Stage" in result.markdown
    assert "# Python comment, not an H1." in result.markdown
    assert "> Review high-risk results" in result.markdown


def test_llm_runs_after_deterministic_repair_when_errors_remain():
    markdown = """## HTTP Headers

Content.

```python
print("hello")
"""

    calls = []

    def llm_repair(current: str, errors: list[str]) -> str:
        calls.append((current, errors))

        assert "## HTTP Headers" not in current
        assert any("unclosed code fence" in error.lower() for error in errors)

        return """Content.

### Example

The repaired section is valid.
"""

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="HTTP Headers",
        llm_repair=llm_repair,
    )

    assert result.errors == []
    assert len(calls) == 1
    assert result.deterministic_repair_applied is True
    assert result.llm_repair_applied is True


def test_llm_is_not_called_when_deterministic_repair_is_enough():
    markdown = """## HTTP Headers

Content.
"""

    def llm_repair(current: str, errors: list[str]) -> str:
        raise AssertionError("LLM repair should not be called.")

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="HTTP Headers",
        llm_repair=llm_repair,
    )

    assert result.errors == []
    assert result.deterministic_repair_applied is True
    assert result.llm_repair_applied is False


def test_invalid_markdown_is_not_formatted_before_repair_succeeds(monkeypatch):
    def fail_if_called(markdown: str) -> str:
        raise AssertionError("Invalid Markdown must not reach mdformat.")

    monkeypatch.setattr(
        markdown_quality,
        "format_markdown",
        fail_if_called,
    )

    result = run_markdown_quality_gate(
        """# Blog

## Wrong Section

Content.
""",
        profile="article",
        expected_title="Blog",
        expected_sections=["Expected Section"],
    )

    assert result.errors
    assert any(
        "Article sections do not match the planned section order." in error
        for error in result.errors
    )


def test_gate_revalidates_after_formatting(monkeypatch):
    valid_markdown = """# Blog

## First

Content.
"""

    def return_invalid_markdown(markdown: str) -> str:
        return """# Blog

## Wrong

Content.
"""

    monkeypatch.setattr(
        markdown_quality,
        "format_markdown",
        return_invalid_markdown,
    )

    result = run_markdown_quality_gate(
        valid_markdown,
        profile="article",
        expected_title="Blog",
        expected_sections=["First"],
    )

    assert result.errors
    assert any(
        "Article sections do not match the planned section order." in error
        for error in result.errors
    )


def test_outer_markdown_wrapper_is_removed_before_success():
    markdown = """```markdown
# Blog

## First

Content.
```"""

    result = run_markdown_quality_gate(
        markdown,
        profile="article",
        expected_title="Blog",
        expected_sections=["First"],
    )

    assert result.errors == []
    assert result.deterministic_repair_applied is True
    assert not result.markdown.startswith("```markdown")


def test_invalid_llm_repair_remains_failed():
    markdown = """Content.

```python
print("hello")
"""

    def llm_repair(current: str, errors: list[str]) -> str:
        return "# Still invalid for a section body\n"

    result = run_markdown_quality_gate(
        markdown,
        profile="section",
        expected_title="Example",
        llm_repair=llm_repair,
    )

    assert result.errors
    assert result.llm_repair_applied is True
    assert any("cannot contain H1" in error for error in result.errors)
