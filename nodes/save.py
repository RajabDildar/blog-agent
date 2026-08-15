from schemas.state import State
from services.storage import publish_blog


def save_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Save: plan is missing.")

    if not state["final_validation_passed"]:
        raise RuntimeError("Refusing to save because final validation failed.")

    run_id = state["run_id"]

    if not run_id:
        raise ValueError("Save: run_id is missing.")

    markdown = state["final"].strip()

    if not markdown:
        raise RuntimeError("Refusing to save empty Markdown.")

    path = publish_blog(
        title=plan.blog_title,
        markdown=markdown,
        run_id=run_id,
        image_results=state.get(
            "image_results",
            [],
        ),
    )

    return {
        "saved_path": str(path),
    }
