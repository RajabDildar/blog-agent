from services.markdown_validation import validate_article_markdown


def test_valid_markdown():
    markdown = """# Test Blog

## First Section

Some content.

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


def test_detects_multiple_h1():
    markdown = """# Test Blog

# Another Title

## Section
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "Section",
        ],
    )

    assert any("exactly one H1" in error for error in errors)


def test_detects_unclosed_code_fence():
    markdown = """# Test Blog

## Section

```python
print("hello")
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "Section",
        ],
    )

    assert any("Unclosed Markdown code fence" in error for error in errors)


def test_detects_wrong_heading_level():
    markdown = """# Test Blog

### Section

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_sections=[
            "Section",
        ],
    )

    assert any("Invalid heading level" in error for error in errors)
