from blog_agent.schemas.state import State
from blog_agent.services.storage import publish_blog


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

    context = {}
    try:
        from langgraph.runtime import get_runtime
        runtime = get_runtime()
        if runtime and runtime.context:
            context = runtime.context
    except Exception:
        pass

    article_repo = context.get("article_repository")
    image_storage = context.get("image_storage")

    path = publish_blog(
        title=plan.blog_title,
        markdown=markdown,
        run_id=run_id,
        image_results=state.get(
            "image_results",
            [],
        ),
        article_repo=article_repo,
        image_storage=image_storage,
    )

    return {
        "saved_path": str(path),
    }
