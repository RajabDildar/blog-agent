from nodes.validator import validate_markdown


def test_valid_markdown():
    markdown = """# Test Blog

## First Section

Some content.

## Second Section

More content.
"""

    errors = validate_markdown(
        markdown,
        expected_sections=[
            "First Section",
            "Second Section",
        ],
        image_results=[],
    )

    assert errors == []


def test_detects_multiple_h1():
    markdown = """# Test Blog

# Another Title

## Section
"""

    errors = validate_markdown(
        markdown,
        expected_sections=[
            "Section",
        ],
        image_results=[],
    )

    assert any("exactly one H1" in error for error in errors)


def test_detects_unclosed_code_fence():
    markdown = """# Test Blog

## Section

```python
print("hello")
"""

    errors = validate_markdown(
        markdown,
        expected_sections=[
            "Section",
        ],
        image_results=[],
    )

    assert any("Unclosed Markdown code fence" in error for error in errors)


def test_detects_wrong_heading_level():
    markdown = """# Test Blog

### Section

Content.
"""

    errors = validate_markdown(
        markdown,
        expected_sections=[
            "Section",
        ],
        image_results=[],
    )

    assert any("Invalid heading level" in error for error in errors)
