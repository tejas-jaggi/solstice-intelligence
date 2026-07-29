"""Solstice Intelligence — presentation layer (Streamlit).

A thin client over the frozen /v1 REST API. It owns presentation, interaction,
and REST communication — and no business logic, SQL, validation, or
orchestration (those live behind the API). It never imports backend modules.

Request lifecycle state machine (governs the submit button, prevents duplicate
submissions and duplicate token spend):

    Idle → Submitting → Waiting → Response → Idle

The transcript in session_state is RENDER-ONLY: each ask sends exactly one
question to the backend; prior turns are never concatenated or resent. This gives
the feel of a conversation with zero extra token cost and no multi-turn
complexity (conversation memory is deferred).
"""
from __future__ import annotations

import httpx
import streamlit as st

from frontend import components, config
from frontend.api_client import RealApiClient
from frontend.models import AnalyticsApiClient, ApiResult


# -- lightweight, cached backend identity (fetched once per session) ---------

def _fetch_version() -> tuple[str | None, str | None]:
    try:
        r = httpx.get(f"{config.API_BASE_URL}/version", timeout=config.REQUEST_TIMEOUT_SECONDS)
        if r.status_code == 200:
            body = r.json()
            return body.get("app_version"), body.get("milestone")
    except httpx.HTTPError:
        pass
    return None, None


def _init_state() -> None:
    st.session_state.setdefault("phase", "idle")        # Idle|Submitting|Waiting|Response
    st.session_state.setdefault("transcript", [])       # render-only history
    st.session_state.setdefault("pending_question", None)


def run(client: AnalyticsApiClient | None = None) -> None:
    """Render and drive the app. A client may be injected (tests); else the real one."""
    st.set_page_config(
        page_title=config.PAGE_TITLE, page_icon=config.PAGE_ICON, layout=config.PAGE_LAYOUT
    )
    _init_state()
    api: AnalyticsApiClient = client or RealApiClient()

    # Header: title + versioned-software identity + readiness (all informational).
    st.title("🌞 Solstice Intelligence")
    st.caption("Ask a question in plain English. Every answer is warehouse-computed, "
               "validated, and shown with the exact SQL that ran.")
    app_version, milestone = _fetch_version()
    components.render_version(app_version, milestone)
    components.render_readiness(api.ready())

    st.divider()

    # Input. The submit button is disabled unless we are Idle (lifecycle rule).
    idle = st.session_state["phase"] == "idle"
    question = st.text_input(
        "Your question",
        placeholder="e.g. How many orders are in the warehouse?",
        disabled=not idle,
    )
    submitted = st.button("Ask", disabled=not idle or not question.strip())

    if submitted and idle and question.strip():
        # Idle -> Submitting -> Waiting (call) -> Response
        st.session_state["phase"] = "waiting"
        with st.spinner("Thinking…"):
            outcome = api.ask(question.strip())  # exactly one question; no history sent
        st.session_state["transcript"].append((question.strip(), outcome))
        st.session_state["phase"] = "idle"       # back to Idle for the next question

    # Render transcript newest-first (render-only; nothing here is resent).
    for q, outcome in reversed(st.session_state["transcript"]):
        st.divider()
        st.markdown(f"**You asked:** {q}")
        if isinstance(outcome, ApiResult):
            components.render_result(outcome)
        else:
            components.render_transport_error(outcome)


if __name__ == "__main__":  # pragma: no cover
    run()
