from services.section_validation import (
    validate_section_markdown,
)


def test_valid_section_body():
    markdown = """Content here.

### Useful Subsection

More detail.
"""

    assert validate_section_markdown(markdown) == []


def test_rejects_h1():
    errors = validate_section_markdown("# Wrong\n\nContent.")

    assert any("cannot contain H1" in error for error in errors)


def test_rejects_h2():
    errors = validate_section_markdown("## Wrong\n\nContent.")

    assert any("cannot contain H2" in error for error in errors)


def test_allows_h3_and_h4():
    markdown = """Intro.

### Request Headers

Content.

#### Example

More content.
"""

    assert validate_section_markdown(markdown) == []


def test_heading_like_code_does_not_fail():
    markdown = """Example:

```python
# comment
## another comment
```
"""

    assert validate_section_markdown(markdown) == []


def test_rejects_unclosed_fence():
    markdown = """Example:

```python
print("hello")
"""

    errors = validate_section_markdown(markdown)

    assert any("unclosed code fence" in error.lower() for error in errors)
