from schemas.state import State
from services.storage import save_blog


def save_node(
    state: State,
) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Save: plan is missing.")

    if not state["final_validation_passed"]:
        raise RuntimeError("Refusing to save because final validation failed.")

    markdown = state["final"].strip()

    if not markdown:
        raise RuntimeError("Refusing to save empty Markdown.")

    try:
        path = save_blog(
            title=plan.blog_title,
            markdown=markdown,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to save blog: {exc}") from exc

    return {
        "saved_path": str(path),
    }
