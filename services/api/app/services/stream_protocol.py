# File purpose: Implements the stream protocol backend service workflow.
# Main declarations: sse handles sse; runtime_diagnostics handles runtime diagnostics.

import json

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def runtime_diagnostics(adapter: object, artifact_discovery_summary: dict[str, object]) -> dict:
    diagnostics = (
        adapter.get_last_diagnostics()
        if adapter is not None and hasattr(adapter, "get_last_diagnostics")
        else {}
    )
    return {
        "artifactDiscovery": artifact_discovery_summary,
        "runtimeDiagnostics": diagnostics,
    }
