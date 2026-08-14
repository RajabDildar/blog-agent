from schemas.state import State


def merge_content(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Merge: plan is missing.")

    sections = state["sections"]

    missing = [task.id for task in plan.tasks if task.id not in sections]

    if missing:
        raise ValueError(f"Merge cannot continue. Missing sections: {missing}")

    rendered_sections: list[str] = []

    for task in plan.tasks:
        body = sections[task.id].body_markdown.strip()

        if not body:
            raise ValueError(f"Merge: section {task.id} is empty.")

        rendered_sections.append(f"## {task.title}\n\n{body}")

    merged_md = f"# {plan.blog_title}\n\n" + "\n\n".join(rendered_sections) + "\n"

    return {
        "merged_md": merged_md,
    }
