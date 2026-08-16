from typing import TypedDict

from services.run_diagnostics import RunDiagnostics


class RunContext(TypedDict):
    diagnostics: RunDiagnostics
