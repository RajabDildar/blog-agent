from services.markdown_validation import (
    validate_article_markdown,
)


def test_valid_complex_article_passes():
    markdown = """# Vector Databases

## Why They Exist

Vector databases support semantic search.

### Query Flow

#### Candidate Ranking

| Stage | Purpose |
| --- | --- |
| Search | Find candidates |
| Rank | Order results |

```python
# This is code, not an article H1.
## This is also code, not an H2.
results = search(query)
```

> Approximate nearest-neighbor search trades some exactness for speed.

- Index
  - partitions
  - metadata filters

## Operational Tradeoffs

Read the [deployment guide](https://example.com/deployment) before production use.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="Vector Databases",
        expected_sections=[
            "Why They Exist",
            "Operational Tradeoffs",
        ],
    )

    assert errors == []


def test_heading_syntax_inside_code_does_not_change_article_structure():
    markdown = """# FastAPI vs Node.js

## Runtime Model

```python
# Fake H1
## Fake H2
```

## Concurrency

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="FastAPI vs Node.js",
        expected_sections=[
            "Runtime Model",
            "Concurrency",
        ],
    )

    assert errors == []


def test_detects_wrong_h1_title():
    markdown = """# Wrong Title

## Detection

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="AI Fraud Detection",
        expected_sections=["Detection"],
    )

    assert any("Expected H1" in error for error in errors)


def test_detects_wrong_h2_order():
    markdown = """# Blog

## Second

Content.

## First

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="Blog",
        expected_sections=[
            "First",
            "Second",
        ],
    )

    assert any(
        "Article sections do not match the planned section order." in error
        for error in errors
    )


def test_detects_missing_planned_section():
    markdown = """# Blog

## First

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="Blog",
        expected_sections=[
            "First",
            "Second",
        ],
    )

    assert any("Section 2" in error for error in errors)


def test_requires_document_to_begin_with_planned_h1():
    markdown = """Intro text that should not be before the title.

# Blog

## First

Content.
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="Blog",
        expected_sections=["First"],
    )

    assert "Document must begin with the planned H1 title." in errors


def test_detects_unclosed_tilde_fence():
    markdown = """# Blog

## First

~~~python
print("hello")
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="Blog",
        expected_sections=["First"],
    )

    assert any("Unclosed Markdown code fence" in error for error in errors)


def test_detects_internal_generation_marker():
    markdown = """# Blog

## First

[[IMAGE_1]]
"""

    errors = validate_article_markdown(
        markdown,
        expected_title="Blog",
        expected_sections=["First"],
    )

    assert "Unresolved image placeholder." in errors
