import mdformat


def normalize_markdown(
    markdown: str,
) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    text = text.removeprefix("\ufeff")

    text = text.strip("\n")

    if not text.strip():
        return ""

    return text + "\n"


def format_markdown(
    markdown: str,
) -> str:
    return mdformat.text(
        markdown,
        extensions={"gfm"},
    )
