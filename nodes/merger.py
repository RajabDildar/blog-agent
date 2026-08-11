from schemas.state import State


def merge_content(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Plan missing")

    sections = state["sections"]

    ordered = [sections[task.id] for task in plan.tasks if task.id in sections]

    body = "\n\n".join(section.markdown.strip() for section in ordered)

    return {"merged_md": (f"# {plan.blog_title}\n\n{body}\n")}
