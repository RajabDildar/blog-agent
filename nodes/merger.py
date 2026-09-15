from schemas.state import State
from services.article_structure import plan_requires_sources
from services.citation_verification import normalize_url


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

    if plan_requires_sources(plan):
        evidence_by_id = {item.id: item for item in state.get("evidence", [])}

        referenced_evidence_ids: list[int] = []
        for task in plan.tasks:
            for ref in task.evidence_refs:
                if ref not in referenced_evidence_ids:
                    referenced_evidence_ids.append(ref)

        source_lines: list[str] = []
        seen_urls: set[str] = set()

        for ref in referenced_evidence_ids:
            item = evidence_by_id.get(ref)
            if item is not None and item.url:
                norm_url = normalize_url(item.url)
                if norm_url not in seen_urls:
                    seen_urls.add(norm_url)
                    source_title = item.source_title.strip() or "Source"
                    source_lines.append(f"- [{source_title}]({item.url})")

        sources_body = "\n".join(source_lines)
        rendered_sections.append(f"## Sources\n\n{sources_body}")

    merged_md = f"# {plan.blog_title}\n\n" + "\n\n".join(rendered_sections) + "\n"

    return {
        "merged_md": merged_md,
    }
