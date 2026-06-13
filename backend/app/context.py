"""Request-scoped context propagated via contextvars.

contextvars (unlike threading.local) propagate correctly through async/await and,
with contextvars.copy_context(), across ThreadPoolExecutor / run_in_executor
boundaries. This is the single source of truth for the current client_id and
request_id so both the agent tools and the logging filter read the same values.
"""

import contextvars

# Identifies the calling client/surface (web, alexa-<user>, task-<id>). Used to key
# the Vertex per-(client_id, agent_id) session pool, so it MUST be correct across
# the executor boundary the task runner crosses.
client_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "client_id", default="default"
)

# Correlates every log line emitted while handling one HTTP request.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
