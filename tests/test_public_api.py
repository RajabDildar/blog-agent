import blog_agent
from blog_agent import resume, run


def test_public_api_exports():
    assert hasattr(blog_agent, "run")
    assert hasattr(blog_agent, "resume")
    assert callable(run)
    assert callable(resume)
    assert sorted(blog_agent.__all__) == ["resume", "run"]


def test_public_api_does_not_export_internals():
    assert not hasattr(blog_agent, "generate_run_id")
    assert not hasattr(blog_agent, "State")
    assert not hasattr(blog_agent, "router_node")
