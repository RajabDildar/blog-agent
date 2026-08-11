from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import GlobalImagePlan
from schemas.state import State
from services.cloudflare import cloudflare_generate_image_bytes
from services.llm import llm


def merge_content(state: State) -> dict:
    plan = state["plan"]

    ordered_sections = [
        md
        for _, md in sorted(
            state["sections"],
            key=lambda x: x[0],
        )
    ]

    body = "\n\n".join(ordered_sections).strip()

    merged_md = f"# {plan.blog_title}\n\n{body}\n"

    return {
        "merged_md": merged_md,
    }


DECIDE_IMAGES_SYSTEM = """You are an expert technical editor.
Decide if images/diagrams are needed for THIS blog.

Rules:
- Max 3 images total.
- Each image must materially improve understanding (diagram/flow/table-like visual).
- Insert placeholders exactly: [[IMAGE_1]], [[IMAGE_2]], [[IMAGE_3]].
- If no images needed: md_with_placeholders must equal input and images=[].
- Avoid decorative images; prefer technical diagrams with short labels.
Return strictly GlobalImagePlan.
"""


def decide_images(state: State) -> dict:
    planner = llm.with_structured_output(GlobalImagePlan)

    merged_md = state["merged_md"]
    plan = state["plan"]

    assert plan is not None

    image_plan = planner.invoke(
        [
            SystemMessage(content=DECIDE_IMAGES_SYSTEM),
            HumanMessage(
                content=(
                    f"Blog kind: {plan.blog_kind}\n"
                    f"Topic: {state['topic']}\n\n"
                    "Insert placeholders + propose image prompts.\n\n"
                    f"{merged_md}"
                )
            ),
        ]
    )

    return {
        "md_with_placeholders": image_plan.md_with_placeholders,
        "image_specs": [img.model_dump() for img in image_plan.images],
    }


def generate_and_place_images(state: State) -> dict:
    plan = state["plan"]

    assert plan is not None

    md = state.get("md_with_placeholders") or state["merged_md"]

    image_specs = state.get("image_specs", []) or []

    if not image_specs:
        filename = f"{plan.blog_title}.md"

        Path(filename).write_text(
            md,
            encoding="utf-8",
        )

        return {
            "final": md,
        }

    images_dir = Path("images")
    images_dir.mkdir(exist_ok=True)

    for spec in image_specs:
        placeholder = spec["placeholder"]
        filename = spec["filename"]

        out_path = images_dir / filename

        if not out_path.exists():
            try:
                img_bytes = cloudflare_generate_image_bytes(spec["prompt"])

                out_path.write_bytes(img_bytes)

            except Exception as e:
                prompt_block = (
                    f"> **[IMAGE GENERATION FAILED]** {spec.get('caption', '')}\n>\n"
                    f"> **Alt:** {spec.get('alt', '')}\n>\n"
                    f"> **Prompt:** {spec.get('prompt', '')}\n>\n"
                    f"> **Error:** {e}\n"
                )

                md = md.replace(
                    placeholder,
                    prompt_block,
                )

                continue

        img_md = f"![{spec['alt']}](images/{filename})\n*{spec['caption']}*"

        md = md.replace(
            placeholder,
            img_md,
        )

    filename = f"{plan.blog_title}.md"

    Path(filename).write_text(
        md,
        encoding="utf-8",
    )

    return {
        "final": md,
    }
