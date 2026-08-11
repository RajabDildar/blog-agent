from pathlib import Path


def save_blog(
    *,
    title: str,
    markdown: str,
) -> Path:
    directory = Path("generated_blogs")
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = directory / f"{title}.md"

    path.write_text(
        markdown,
        encoding="utf-8",
    )

    return path
