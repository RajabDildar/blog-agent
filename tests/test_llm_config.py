from services import llm


def test_groq_model_retries_are_disabled():
    assert llm.writer_llm.max_retries == 0
    assert llm.revision_llm.max_retries == 0


def test_gemini_model_retries_are_disabled():
    assert llm.gemini_llm.max_retries == 0
