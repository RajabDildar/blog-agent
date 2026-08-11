from langchain_core.messages import HumanMessage, SystemMessage

from schemas.models import GlobalImagePlan, Plan
from schemas.state import State
from services.image_prompt import build_image_prompt
from services.llm import planner_llm
from services.markdown import safe_filename
from prompts.image import IMAGE_SYSTEM


def image_planner_node(state: State) -> dict:
    plan: Plan | None = state["plan"]

    if plan is None:
        raise ValueError("Plan missing")

    planner = planner_llm.with_structured_output(GlobalImagePlan)

    result = planner.invoke(
        [
            SystemMessage(content=IMAGE_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n\n"
                    f"Plan:\n{plan.model_dump()}\n\n"
                    f"Final article:\n"
                    f"{state['merged_md']}"
                )
            ),
        ]
    )

    image_specs = []

    for image in result.images:
        section_title = next(
            task.title for task in plan.tasks if task.id == image.section_id
        )

        image_data = image.model_dump()

        image_data["prompt"] = build_image_prompt(
            purpose=image.purpose,
            section_title=section_title,
            image_type=image.image_type,
        )

        image_data["filename"] = safe_filename(f"{image.section_id}_{section_title}")

        image_specs.append(image_data)

    return {
        "image_specs": image_specs,
    }
