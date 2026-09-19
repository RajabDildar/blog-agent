from typing import TypedDict

from blog_agent.services.run_diagnostics import RunDiagnostics


class RunContext(TypedDict):
    diagnostics: RunDiagnostics
