from services.markdown_validation import validate_article_markdown

TITLE = "Test Article"
SECTIONS = ["Introduction"]


def test_forbidden_marker_in_normal_text_is_rejected():
    markdown = """# Test Article

## Introduction

This contains [[IMAGE_1]] in normal article text.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title=TITLE,
        expected_sections=SECTIONS,
    )

    assert "Unresolved image placeholder." in errors


def test_forbidden_marker_inside_fenced_code_is_ignored():
    markdown = """# Test Article

## Introduction

```text
[[IMAGE_1]]
IMAGE GENERATION FAILED
Not found in provided sources.
```

Normal content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title=TITLE,
        expected_sections=SECTIONS,
    )

    assert errors == []


def test_forbidden_marker_inside_inline_code_is_ignored():
    markdown = """# Test Article

## Introduction

Use `[[IMAGE_1]]` as an example marker.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title=TITLE,
        expected_sections=SECTIONS,
    )

    assert errors == []


def test_other_forbidden_markers_are_still_rejected():
    markdown = """# Test Article

## Introduction

IMAGE GENERATION FAILED

Not found in provided sources.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title=TITLE,
        expected_sections=SECTIONS,
    )

    assert "Image failure text leaked into output." in errors
    assert "Unsupported claim marker leaked into output." in errors
