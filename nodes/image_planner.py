from langchain_core.messages import HumanMessage, SystemMessage

from prompts.image import IMAGE_SYSTEM
from schemas.models import GlobalImagePlan, Plan
from schemas.state import State
from services.llm import gemini_llm
from services.markdown import safe_filename


def image_planner_node(state: State) -> dict:
    try:
        plan: Plan | None = state["plan"]

        if plan is None:
            raise ValueError("Image planner: plan is missing.")

        if not state["merged_md"].strip():
            raise ValueError("Image planner received empty article.")

        try:
            planner = gemini_llm.with_structured_output(GlobalImagePlan)

            result = planner.invoke(
                [
                    SystemMessage(content=IMAGE_SYSTEM),
                    HumanMessage(
                        content=(
                            f"Topic:\n{state['topic']}\n\n"
                            f"Plan:\n{plan.model_dump()}\n\n"
                            f"Final article:\n{state['merged_md']}"
                        )
                    ),
                ]
            )
        except Exception as exc:
            raise RuntimeError(f"Image planning failed: {exc}") from exc

        image_specs: list[dict] = []

        valid_task_ids = {task.id for task in plan.tasks}

        for image in result.images:
            if image.section_id not in valid_task_ids:
                raise ValueError(
                    f"Image planner returned invalid section_id {image.section_id}."
                )

            task = next(task for task in plan.tasks if task.id == image.section_id)

            image_data = image.model_dump()

            image_data["filename"] = safe_filename(
                f"{image.section_id}_{task.title}_{image.id}"
            )

            image_specs.append(image_data)
    except Exception as exc:
        raise RuntimeError(f"Image planner failed: {exc}") from exc

    return {
        "image_specs": image_specs,
    }
