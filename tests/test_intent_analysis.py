import pytest
from pydantic import ValidationError

from blog_agent.schemas.models import IntentAnalysis, IntentHumanResponse, ProposedTopicAnalysis


def test_intent_analysis_accepted_valid():
    analysis = IntentAnalysis(
        outcome="accepted",
        normalized_topic="Distributed Consensus via Raft",
    )
    assert analysis.outcome == "accepted"
    assert analysis.normalized_topic == "Distributed Consensus via Raft"


def test_intent_analysis_accepted_empty_topic_rejected():
    with pytest.raises(ValidationError) as exc_info:
        IntentAnalysis(
            outcome="accepted",
            normalized_topic="   ",
        )
    assert "accepted outcome requires non-empty normalized_topic" in str(exc_info.value)


def test_intent_analysis_needs_clarification_valid():
    analysis = IntentAnalysis(
        outcome="needs_clarification",
        clarification_question="What area of cloud infrastructure do you want to explore?",
        clarification_options=[
            "Kubernetes multi-cluster orchestration",
            "Serverless event-driven architectures with AWS Lambda",
            "Infrastructure as Code with Terraform and OpenTofu",
        ],
    )
    assert analysis.outcome == "needs_clarification"
    assert len(analysis.clarification_options) == 3


def test_intent_analysis_needs_clarification_requires_exactly_three_options():
    with pytest.raises(ValidationError) as exc_info:
        IntentAnalysis(
            outcome="needs_clarification",
            clarification_question="What topic?",
            clarification_options=[
                "Option 1",
                "Option 2",
            ],
        )
    assert "exactly 3 clarification_options" in str(exc_info.value)


def test_intent_analysis_needs_clarification_requires_distinct_options():
    with pytest.raises(ValidationError) as exc_info:
        IntentAnalysis(
            outcome="needs_clarification",
            clarification_question="What topic?",
            clarification_options=[
                "Option 1",
                "Option 1",
                "Option 2",
            ],
        )
    assert "clarification_options must be distinct" in str(exc_info.value)


def test_intent_analysis_needs_clarification_requires_non_empty_options():
    with pytest.raises(ValidationError) as exc_info:
        IntentAnalysis(
            outcome="needs_clarification",
            clarification_question="What topic?",
            clarification_options=[
                "Option 1",
                "  ",
                "Option 3",
            ],
        )
    assert "clarification_options must be non-empty strings" in str(exc_info.value)


def test_intent_analysis_blocked_valid():
    analysis = IntentAnalysis(
        outcome="blocked",
        block_category="cyber_abuse",
        user_message="I cannot generate instructions for malicious cyber attacks. You can try: Defensive security best practices.",
    )
    assert analysis.outcome == "blocked"
    assert analysis.block_category == "cyber_abuse"


def test_intent_analysis_blocked_missing_category_rejected():
    with pytest.raises(ValidationError) as exc_info:
        IntentAnalysis(
            outcome="blocked",
            user_message="Blocked message",
        )
    assert "blocked outcome requires a supported block_category" in str(exc_info.value)


def test_intent_analysis_invalid_valid():
    analysis = IntentAnalysis(
        outcome="invalid",
        invalid_reason="out_of_scope_non_technical",
        user_message="Blog Agent focuses on technical articles. Please provide a technical topic.",
    )
    assert analysis.outcome == "invalid"
    assert analysis.invalid_reason == "out_of_scope_non_technical"


def test_intent_analysis_invalid_missing_reason_rejected():
    with pytest.raises(ValidationError) as exc_info:
        IntentAnalysis(
            outcome="invalid",
            user_message="Invalid request",
        )
    assert "invalid outcome requires invalid_reason" in str(exc_info.value)


def test_intent_human_response_validation():
    # select_option requires non-empty value
    valid_select = IntentHumanResponse(action="select_option", value="Option A")
    assert valid_select.action == "select_option"
    assert valid_select.value == "Option A"

    with pytest.raises(ValidationError):
        IntentHumanResponse(action="select_option", value="")

    # custom_input requires non-empty value
    valid_custom = IntentHumanResponse(action="custom_input", value="My custom topic")
    assert valid_custom.value == "My custom topic"

    with pytest.raises(ValidationError):
        IntentHumanResponse(action="custom_input", value="   ")

    # proceed and cancel do not require value
    proceed = IntentHumanResponse(action="proceed")
    assert proceed.action == "proceed"

    cancel = IntentHumanResponse(action="cancel")
    assert cancel.action == "cancel"


def test_proposed_topic_analysis_valid():
    pta = ProposedTopicAnalysis(proposed_topic="Advanced PostgreSQL Indexing Strategies")
    assert pta.proposed_topic == "Advanced PostgreSQL Indexing Strategies"
