# Blog Evaluation

Phase 8.7 provides a repeatable baseline evaluation harness.

The evaluator:

1. Loads seed topics from `topics.json`.
2. Runs each topic through the production blog pipeline.
3. Loads the run diagnostics.
4. Scores the generated article with a separately configured judge model.
5. Records successful and failed runs.
6. Writes machine-readable and human-readable reports.

## Scores

Each successful article is scored from 1 to 10 for:

- Overall quality
- Structure
- Technical accuracy
- Research quality
- Coherence
- Usefulness
- Writing quality
- Citations
- Images

## Runtime metrics

Each run records:

- LLM calls
- Research calls
- Image calls
- Revision count
- Generation time
- Retries
- Failure information when applicable

`research_calls` currently represents attempts of the combined `tavily+gemini` research node because the existing diagnostics do not record individual Tavily HTTP requests.

## Judge model

Configure the evaluation judge separately from the production pipeline:

```text
EVAL_JUDGE_MODEL=gemini-3.1-flash-lite