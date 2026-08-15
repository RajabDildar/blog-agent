from pathlib import Path

import nodes.image_generator as image_generator
from nodes.image_generator import generate_images_node
from schemas.models import Plan, Task


RUN_ID = "b" * 32


def make_plan() -> Plan:
    return Plan(
        blog_title="Test Blog",
        thesis="Explain the architecture.",
        opening_angle="Start with the system boundary.",
        reader_promise="The reader will understand the architecture.",
        audience="Software developers",
        tone="Clear and technical",
        tasks=[
            Task(
                id=1,
                title="Architecture",
                goal="Explain the architecture.",
                bullets=[
                    "Components",
                    "Connections",
                    "Data flow",
                ],
                target_words=200,
                section_role="architecture",
            )
        ],
    )


def make_image_spec() -> dict:
    return {
        "id": "architecture",
        "section_id": 1,
        "image_type": "technical_diagram",
        "purpose": "Explain the system architecture.",
        "visual_description": (
            "A technical system architecture diagram showing components "
            "and the data flow between them."
        ),
        "key_elements": [
            "API",
            "worker",
            "storage",
        ],
        "placement": "start",
        "alt": "System architecture diagram",
        "caption": "A simplified system architecture.",
        "filename": "1_architecture_architecture.png",
    }


def test_image_generation_uses_run_staging_not_global_images(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    # Simulate an old file from the pre-run-isolation architecture.
    old_global_dir = tmp_path / "images"
    old_global_dir.mkdir()
    old_global_file = old_global_dir / "1_architecture_architecture.png"
    old_global_file.write_bytes(b"old-image")

    calls = []

    def fake_generate(prompt: str) -> bytes:
        calls.append(prompt)
        return b"new-image"

    inserted_paths = []

    def fake_insert_image(
        *,
        markdown,
        section,
        image,
        image_path,
    ):
        inserted_paths.append(image_path)
        return markdown + f"\n\n![{image.alt}]({image_path})\n"

    monkeypatch.setattr(
        image_generator,
        "cloudflare_generate_image_bytes",
        fake_generate,
    )
    monkeypatch.setattr(
        image_generator,
        "insert_image",
        fake_insert_image,
    )

    result = generate_images_node(
        {
            "run_id": RUN_ID,
            "plan": make_plan(),
            "merged_md": "# Test Blog\n\n## Architecture\n\nContent.\n",
            "image_specs": [make_image_spec()],
        }
    )

    staged = tmp_path / "runs" / RUN_ID / "images" / "1_architecture_architecture.png"
    published = (
        tmp_path / "images" / "test_blog" / RUN_ID / "1_architecture_architecture.png"
    )

    assert len(calls) == 1
    assert staged.read_bytes() == b"new-image"
    assert old_global_file.read_bytes() == b"old-image"
    assert not published.exists()

    image_result = result["image_results"][0]

    assert image_result["staged_path"] == str(
        Path("runs") / RUN_ID / "images" / "1_architecture_architecture.png"
    )
    assert image_result["published_path"] == str(
        Path("images") / "test_blog" / RUN_ID / "1_architecture_architecture.png"
    )
    assert image_result["markdown_path"] == (
        f"../images/test_blog/{RUN_ID}/1_architecture_architecture.png"
    )

    assert inserted_paths == [
        f"../images/test_blog/{RUN_ID}/1_architecture_architecture.png"
    ]
