from schemas.models import ImageSpec
from schemas.state import State
from services.cloudflare import (
    cloudflare_generate_image_bytes,
)
from services.image_prompt import build_image_prompt
from services.markdown import insert_image
from services.run_diagnostics import (
    get_current_diagnostics,
)
from services.run_paths import (
    markdown_image_path,
    published_image_path,
    staged_image_path,
)


def generate_images_node(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Image generator: plan is missing.")

    run_id = state["run_id"]

    if not run_id:
        raise ValueError("Image generator: run_id is missing.")

    markdown = state["merged_md"]

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

        staged_path = staged_image_path(
            run_id=run_id,
            filename=filename,
        )

        published_path = published_image_path(
            title=plan.blog_title,
            run_id=run_id,
            filename=filename,
        )

        markdown_path = markdown_image_path(
            title=plan.blog_title,
            run_id=run_id,
            filename=filename,
        )

        staged_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        prompt = build_image_prompt(
            purpose=spec.purpose,
            visual_description=spec.visual_description,
            key_elements=spec.key_elements,
            section_title=task.title,
            image_type=spec.image_type,
        )

        diagnostics = get_current_diagnostics()

        if diagnostics is not None:
            diagnostics.record_image_attempt(spec.id)

        try:
            image_bytes = cloudflare_generate_image_bytes(prompt)

            if not image_bytes:
                raise RuntimeError("Cloudflare returned empty image bytes.")

            # Always generate this run's own staged file.
            # Never reuse an image from a previous run.
            staged_path.write_bytes(image_bytes)

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
                "staged_path": str(staged_path),
                "published_path": str(published_path),
                "section_id": spec.section_id,
                "status": "inserted",
            }
        )

    return {
        "final": markdown,
        "image_results": image_results,
    }
