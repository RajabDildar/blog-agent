import httpx
import groq
import pytest

from schemas.models import Plan, Task

import nodes.editor as editor
import nodes.image_planner as image_planner
import nodes.orchestrator as orchestrator
import nodes.research as research
import nodes.revision as revision
import nodes.router as router


def make_rate_limit_error() -> groq.RateLimitError:
    request = httpx.Request(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
    )

    response = httpx.Response(
        429,
        request=request,
    )

    return groq.RateLimitError(
        "rate limited",
        response=response,
        body=None,
    )


def make_plan() -> Plan:
    return Plan(
        blog_title="Test",
        thesis="Explain the architecture.",
        opening_angle="Start with the system boundary.",
        reader_promise="The reader will understand the main architecture.",
        audience="Software developers",
        tone="Technical and clear",
        tasks=[
            Task(
                id=1,
                title="Section",
                goal="Explain the architecture clearly.",
                bullets=[
                    "First point",
                    "Second point",
                    "Third point",
                ],
                target_words=100,
                section_role="architecture",
            )
        ],
    )


class FailingModel:
    def with_structured_output(self, *args, **kwargs):
        return self

    def invoke(self, *args, **kwargs):
        raise make_rate_limit_error()


@pytest.mark.parametrize(
    "module",
    [
        router,
        orchestrator,
        research,
        editor,
        image_planner,
        revision,
    ],
)
def test_provider_exception_type_is_preserved(
    monkeypatch,
    module,
):
    monkeypatch.setattr(
        module,
        "gemini_llm" if module is not revision else "revision_llm",
        FailingModel(),
    )

    state = {
        "topic": "Test",
        "mode": "generation",
        "queries": [],
        "research_focus": [],
        "research_brief": "",
        "evidence": [],
        "merged_md": "# Test\n\n## Section\n\nContent.",
        "plan": None,
        "sections": {},
    }

    research_state = {
        **state,
        "queries": ["test query"],
    }

    editor_state = {
        **state,
        "plan": make_plan(),
    }

    image_planner_state = {
        **state,
        "plan": make_plan(),
        "merged_md": ("# Test\n\n## Section\n\nArticle content."),
    }

    monkeypatch.setattr(
        research,
        "tavily_search",
        lambda query, max_results=3: [
            {
                "url": "https://example.com/source",
                "title": "Example Source",
                "score": 1.0,
                "content": "Useful content.",
                "raw_content": "Useful raw content.",
            }
        ],
    )

    if module is router:
        call = lambda: router.router_node({"topic": "Test"})
    elif module is orchestrator:
        call = lambda: orchestrator.orchestrator_node(state)
    elif module is research:
        call = lambda: research.research_node(research_state)
    elif module is editor:
        call = lambda: editor.editor_node(editor_state)
    elif module is image_planner:
        call = lambda: image_planner.image_planner_node(image_planner_state)
    else:
        call = lambda: revision.revision_node(
            {
                "task": {
                    "id": 1,
                    "title": "Section",
                    "goal": "Explain the architecture clearly.",
                    "bullets": [
                        "First point",
                        "Second point",
                        "Third point",
                    ],
                    "target_words": 100,
                    "section_role": "architecture",
                },
                "section": "Content.",
                "issues": [],
            }
        )

    with pytest.raises(groq.RateLimitError):
        call()
