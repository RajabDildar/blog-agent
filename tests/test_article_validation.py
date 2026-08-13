from services.markdown_validation import (
    validate_article_markdown,
)


def test_valid_article():
    markdown = """# My Article

## First Section

Content.

## Second Section

More content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "First Section",
            "Second Section",
        ],
    )

    assert errors == []


def test_multiple_h1():
    markdown = """# My Article

# Another Title

## First Section

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "First Section",
        ],
    )

    assert any("exactly one H1" in error for error in errors)


def test_h3_rejected():
    markdown = """# My Article

## First Section

### Subsection

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "First Section",
        ],
    )

    assert any("Invalid heading level" in error for error in errors)


def test_wrong_section_order():
    markdown = """# My Article

## Second Section

Content.

## First Section

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "First Section",
            "Second Section",
        ],
    )

    assert any("section order" in error.lower() for error in errors)


def test_unclosed_code_fence():
    markdown = """# My Article

## First Section

```python
print("hello")
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "First Section",
        ],
    )

    assert any("Unclosed Markdown code fence" in error for error in errors)
