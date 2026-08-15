import pytest

from services.markdown_parser import (
    find_unclosed_fence,
    get_headings,
    get_image_sources,
    has_fenced_code,
    has_gfm_table,
    parse_markdown,
)


def test_parse_markdown_returns_tokens():
    tokens = parse_markdown("# Hello\n\nThis is **bold**.")

    assert tokens
    assert tokens[0].type == "heading_open"
    assert tokens[0].tag == "h1"


def test_get_headings_returns_level_text_and_line():
    markdown = """# Introduction

Some text.

## Installation

More text.

### Usage
"""

    assert get_headings(markdown) == [
        # Heading text is taken from the inline token content.
        type(get_headings("# x")[0])(level=1, text="Introduction", line=1),
        type(get_headings("# x")[0])(level=2, text="Installation", line=5),
        type(get_headings("# x")[0])(level=3, text="Usage", line=9),
    ]


def test_get_headings_returns_empty_list_when_no_headings():
    markdown = "Just a paragraph.\n\nAnother paragraph."

    assert get_headings(markdown) == []


def test_get_headings_ignores_heading_syntax_inside_backtick_fence():
    markdown = """# Real Title

```python
# Python comment
## Still a Python comment
```

## Real Section
"""

    headings = get_headings(markdown)

    assert [(heading.level, heading.text) for heading in headings] == [
        (1, "Real Title"),
        (2, "Real Section"),
    ]


def test_get_headings_ignores_heading_syntax_inside_tilde_fence():
    markdown = """# Real Title

~~~bash
# shell comment
## not a Markdown section
~~~

## Real Section
"""

    headings = get_headings(markdown)

    assert [(heading.level, heading.text) for heading in headings] == [
        (1, "Real Title"),
        (2, "Real Section"),
    ]


def test_get_image_sources_returns_image_urls():
    markdown = """# Blog

![First image](https://example.com/first.png)

Some text.

![Second image](/images/second.webp)
"""

    assert get_image_sources(markdown) == [
        "https://example.com/first.png",
        "/images/second.webp",
    ]


def test_get_image_sources_returns_empty_list_when_no_images():
    markdown = "No images here."

    assert get_image_sources(markdown) == []


def test_get_image_sources_ignores_image_syntax_inside_code():
    markdown = """# Blog

```markdown
![not-an-article-image](../images/example.png)
```

![real image](../images/real.png)
"""

    assert get_image_sources(markdown) == [
        "../images/real.png",
    ]


def test_get_image_sources_preserves_duplicate_references():
    markdown = """![first](../images/shared.png)

![second](../images/shared.png)
"""

    assert get_image_sources(markdown) == [
        "../images/shared.png",
        "../images/shared.png",
    ]


def test_has_gfm_table_returns_true_for_table():
    markdown = """| Name | Age |
| --- | ---: |
| Rajab | 25 |
"""

    assert has_gfm_table(markdown) is True


def test_has_gfm_table_returns_false_for_non_table():
    markdown = """# Heading

This is a paragraph.
"""

    assert has_gfm_table(markdown) is False


def test_has_gfm_table_ignores_table_like_text_inside_code():
    markdown = """```markdown
| Name | Age |
| --- | --- |
| Ada | 36 |
```
"""

    assert has_gfm_table(markdown) is False


def test_has_fenced_code_returns_true_for_fenced_code():
    markdown = """```python
print("hello")
```
"""

    assert has_fenced_code(markdown) is True


def test_has_fenced_code_returns_true_for_tilde_fence():
    markdown = """~~~python
print("hello")
~~~
"""

    assert has_fenced_code(markdown) is True


def test_has_fenced_code_returns_false_for_inline_code():
    markdown = "Use `print()` to output text."

    assert has_fenced_code(markdown) is False


@pytest.mark.parametrize(
    "markdown, expected_line",
    [
        ("```python\nprint('hello')", 1),
        ("~~~\ncode", 1),
        ("# Heading\n\n```js\nconst x = 1;", 3),
        ("text\n  ```python\n  code", 2),
    ],
)
def test_find_unclosed_fence_detects_unclosed_fences(markdown, expected_line):
    assert find_unclosed_fence(markdown) == expected_line


@pytest.mark.parametrize(
    "markdown",
    [
        "```python\nprint('hello')\n```",
        "~~~\ncode\n~~~",
        "# Heading\n\n```js\nconst x = 1;\n```\n",
        "```python\ncode\n````\n",
    ],
)
def test_find_unclosed_fence_returns_none_for_closed_fences(markdown):
    assert find_unclosed_fence(markdown) is None


def test_find_unclosed_fence_accepts_longer_matching_closing_fence():
    markdown = """````python
print("hello")
`````
"""

    assert find_unclosed_fence(markdown) is None


def test_find_unclosed_fence_does_not_close_with_shorter_fence():
    markdown = """````python
print("hello")
```
"""

    assert find_unclosed_fence(markdown) == 1


def test_find_unclosed_fence_does_not_close_backtick_fence_with_extra_text():
    markdown = """```python
print("hello")
``` trailing text
"""

    assert find_unclosed_fence(markdown) == 1


def test_find_unclosed_fence_does_not_open_backtick_fence_with_backtick_in_info():
    markdown = """```python`extra
print("hello")
"""

    assert find_unclosed_fence(markdown) is None


def test_find_unclosed_fence_supports_up_to_three_leading_spaces():
    markdown = """   ```python
   print("hello")
   ```
"""

    assert find_unclosed_fence(markdown) is None


def test_find_unclosed_fence_ignores_four_leading_spaces():
    markdown = """    ```python
    print("hello")
    """

    assert find_unclosed_fence(markdown) is None


def test_find_unclosed_fence_handles_multiple_fences():
    markdown = """```python
print("first")
```
~~~javascript
console.log("second")
~~~
"""

    assert find_unclosed_fence(markdown) is None


def test_find_unclosed_fence_reports_second_unclosed_fence():
    markdown = """```python
print("first")
```

~~~javascript
console.log("second")
"""

    assert find_unclosed_fence(markdown) == 5
