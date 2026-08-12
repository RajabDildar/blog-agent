from pathlib import Path

from schemas.models import ImageSpec
from schemas.state import State
from services.cloudflare import (
    cloudflare_generate_image_bytes,
)
from services.image_prompt import build_image_prompt
from services.markdown import insert_image


def generate_images_node(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Image generator: plan is missing.")

    markdown = state["merged_md"]

    images_dir = Path("images")

    images_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    image_results: list[dict] = []

    for raw_spec in state.get(
        "image_specs",
        [],
    ):
        spec = ImageSpec(**raw_spec)

        task = next(
            (task for task in plan.tasks if task.id == spec.section_id),
            None,
        )

        if task is None:
            raise ValueError(
                f"Image {spec.id} references unknown section {spec.section_id}."
            )

        filename = raw_spec["filename"]

        output_path = images_dir / filename

        markdown_path = f"../images/{filename}"

        prompt = build_image_prompt(
            purpose=spec.purpose,
            visual_description=spec.visual_description,
            key_elements=spec.key_elements,
            section_title=task.title,
            image_type=spec.image_type,
        )

        if not output_path.exists():
            try:
                image_bytes = cloudflare_generate_image_bytes(prompt)

                if not image_bytes:
                    raise RuntimeError("Cloudflare returned empty image bytes.")

                output_path.write_bytes(image_bytes)

            except Exception as exc:
                raise RuntimeError(
                    f"Image generation failed for {spec.id} ({filename}): {exc}"
                ) from exc

        try:
            markdown = insert_image(
                markdown=markdown,
                section=task.title,
                image=spec,
                image_path=markdown_path,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Image insertion failed for {spec.id} in section '{task.title}': {exc}"
            ) from exc

        image_results.append(
            {
                "id": spec.id,
                "filename": filename,
                "markdown_path": markdown_path,
                "section_id": spec.section_id,
                "status": "inserted",
            }
        )

    return {
        "final": markdown,
        "image_results": image_results,
    }
