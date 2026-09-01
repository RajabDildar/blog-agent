from services.source_quality import classify_source


def test_official_documentation_gets_high_authority():
    result = classify_source("https://fastapi.tiangolo.com/tutorial/")

    assert result.source_type == "official_documentation"
    assert result.authority_score >= 0.9


def test_government_source_gets_high_authority():
    result = classify_source("https://www.nist.gov/ai")

    assert result.source_type == "government_source"
    assert result.authority_score >= 0.9


def test_github_repository_is_classified():
    result = classify_source("https://github.com/langchain-ai/langchain")

    assert result.source_type == "github_repository"
    assert result.authority_score == 0.90


def test_vendor_blog_is_lower_authority():
    result = classify_source("https://example.com/blog/ai-trends")

    assert result.source_type == "vendor_blog"
    assert result.authority_score < 0.7


def test_unknown_source_is_low_confidence():
    result = classify_source("https://random-example-site.com/article")

    assert result.source_type == "unknown"
    assert result.authority_score < 0.5


def test_official_documentation_scores_high():
    result = classify_source("https://docs.langchain.com/langgraph")

    assert result.source_type == "official_documentation"
    assert result.authority_score >= 0.9


def test_government_sources_score_high():
    result = classify_source("https://www.nist.gov/publications/example")

    assert result.source_type == "government_source"
    assert result.authority_score >= 0.9


def test_official_github_repository_scores_higher():
    result = classify_source("https://github.com/langchain-ai/langgraph")

    assert result.source_type == "github_repository"
    assert result.authority_score >= 0.85


def test_unknown_sources_score_lower():
    result = classify_source("https://example.com/article")

    assert result.source_type == "unknown"
    assert result.authority_score < 0.5


def test_low_quality_publishing_platforms_are_penalized():
    result = classify_source("https://medium.com/example/article")

    assert result.source_type == "vendor_blog"
    assert result.authority_score <= 0.3
