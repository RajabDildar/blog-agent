import json
import time
from pathlib import Path


class RunMetrics:
    def __init__(self):
        self.started_at = time.time()

        self.llm_calls = 0
        self.research_calls = 0
        self.image_calls = 0
        self.revision_count = 0

    def finish(self) -> dict:
        return {
            "duration_seconds": round(
                time.time() - self.started_at,
                2,
            ),
            "llm_calls": self.llm_calls,
            "research_calls": self.research_calls,
            "image_calls": self.image_calls,
            "revision_count": self.revision_count,
        }


def save_metrics(
    *,
    topic: str,
    metrics: dict,
):
    directory = Path("eval/runs")
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = topic.lower().replace(" ", "_") + ".json"

    path = directory / filename

    path.write_text(
        json.dumps(
            metrics,
            indent=2,
        ),
        encoding="utf-8",
    )
