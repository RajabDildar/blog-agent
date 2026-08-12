from schemas.state import State


def merge_content(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Merge: plan is missing.")

    sections = state["sections"]

    missing = [task.id for task in plan.tasks if task.id not in sections]

    if missing:
        raise ValueError(f"Merge cannot continue. Missing sections: {missing}")

    ordered = [sections[task.id] for task in plan.tasks]

    body = "\n\n".join(section.markdown.strip() for section in ordered)

    return {"merged_md": (f"# {plan.blog_title}\n\n{body}\n")}
