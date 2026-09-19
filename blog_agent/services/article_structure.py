from blog_agent.schemas.models import Plan


def plan_requires_sources(plan: Plan) -> bool:
    """Return True if any task in the plan references research evidence."""
    return any(bool(task.evidence_refs) for task in plan.tasks)


def get_expected_sections(plan: Plan) -> list[str]:
    """
    Get expected H2 section titles for an article built from the plan.
    Appends 'Sources' as the final section if any task uses evidence.
    """
    sections = [task.title.strip() for task in plan.tasks]
    if plan_requires_sources(plan):
        sections.append("Sources")
    return sections
