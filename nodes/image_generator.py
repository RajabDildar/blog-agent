from pathlib import Path

from schemas.models import ImageSpec
from schemas.state import State
from services.cloudflare import (
    cloudflare_generate_image_bytes,
)
from services.markdown import insert_image
from services.storage import save_blog


def generate_images_node(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Plan missing")

    markdown = state["merged_md"]

    images_dir = Path("images")
    images_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for raw_spec in state.get(
        "image_specs",
        [],
    ):
        spec = ImageSpec(**raw_spec)

        task = next(task for task in plan.tasks if task.id == spec.section_id)

        filename = raw_spec["filename"]
        prompt = raw_spec["prompt"]

        output_path = images_dir / filename

        if not output_path.exists():
            try:
                image_bytes = cloudflare_generate_image_bytes(prompt)

                output_path.write_bytes(image_bytes)

            except Exception as exc:
                print(f"Image generation failed for {filename}: {exc}")
                continue

        markdown = insert_image(
            markdown=markdown,
            section=task.title,
            image=spec,
            image_path=f"../images/{filename}",
        )

    save_blog(
        title=plan.blog_title,
        markdown=markdown,
    )

    return {
        "final": markdown,
    }
