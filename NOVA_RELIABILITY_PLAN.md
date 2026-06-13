# NOVA — Reliability & Hardening Plan

**Goal:** Keep NOVA personal/single-user, but make it stop breaking on you — and close the security holes that matter *because the box is already on the public internet* via Cloudflare Tunnel.

**Scope deliberately cut:** No user accounts, no multi-tenant data isolation, no RBAC, no vector-search brain, no frontend rewrite. Those are real but they are not your problem right now.

**Timeline:** ~3 weeks of steady part-time work, phased so each week ends with NOVA more stable than it started — nothing here requires a big-bang rewrite.

---

## How to read this

Everything is ordered by **(risk it bites you) × (cheapness to fix)**. The first week is almost entirely "stop the bleeding" — small, surgical changes. Weeks 2–3 are the structural reliability work that actually addresses "it breaks on me."

Each item has: **why it bites you**, **the fix**, and a rough **effort** (S = under an hour, M = a few hours, L = a day-ish).

---

## Week 1 — Stop the bleeding

These are small and high-leverage. Three are security holes that exist *today* because your tunnel exposes the box; the rest are reliability quick wins.

### 1.1 — Fix the `X-Forwarded-For` auth bypass `[S, security-critical]`

**Why it bites you:** In `main.py`, `api_key_guard` trusts a client-supplied `X-Forwarded-For` header to decide "is this LAN?". Anyone on the internet can send `X-Forwarded-For: 192.168.1.5` and your code waves them through with no API key. The tunnel makes this reachable from anywhere.

**The fix:**
- Only trust forwarding headers from the tunnel. Cloudflare sets `CF-Connecting-IP` authoritatively — read that instead of the first hop of `X-Forwarded-For`.
- If you keep `X-Forwarded-For`, only honor it when `request.client.host` is in Cloudflare's published IP ranges (or `127.0.0.1`, since the tunnel daemon runs locally and connects to NOVA over loopback — meaning *every* tunnelled request already looks like LAN to you, which is the deeper bug).
- Practical single-user version: since the tunnel hits you over loopback, "is LAN" can no longer mean "trust." Require the API key for **any** request that arrived through the tunnel, and only treat *actual* LAN interface IPs as trusted. Test it: `curl -H "X-Forwarded-For: 10.0.0.1" https://<your-tunnel>/api/settings/keychain/list` should return 401, not your secrets.

### 1.2 — Put auth in front of the keychain & settings endpoints `[S, security-critical]`

**Why it bites you:** `/api/settings/keychain/list`, `/set`, `/import`, and all the credential routes have no auth of their own — they rely entirely on the (now-broken) LAN check. `keychain/list` enumerates every secret name; `keychain/import` will sweep your `.env` into the keychain on demand.

**The fix:** Require the API key on everything under `/api/settings` regardless of source IP. The cleanest way is a FastAPI dependency on the settings router:
```python
from fastapi import Depends, Header, HTTPException
def require_api_key(authorization: str = Header("")):
    token = authorization.removeprefix("Bearer ").strip()
    if not settings.nova_api_key or token != settings.nova_api_key:
        raise HTTPException(401, "API key required")
router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_api_key)])
```
Single-user, so one shared key is fine — the point is that "on my LAN" stops being a free pass for secret management.

### 1.3 — Verify Alexa requests (or take the endpoint off the public list) `[M, security-critical]`

**Why it bites you:** `/alexa` is in `_PUBLIC_PATHS` — no key, no signature check. `routes_alexa.py` does `body = await req.json()` and runs your agent on whatever it gets. Anyone who finds the URL can send email, hit your calendar, and control your smart home by POSTing fake Alexa JSON.

**The fix (pick one):**
- **Proper:** validate the `Signature-256` + `SignatureCertChainUrl` headers and the request timestamp (Amazon's standard skill verification). The `python` libraries `ask-sdk-webservice-support` or a small manual cert-chain check both work.
- **Pragmatic for now:** if you're not actively using Alexa, remove `/alexa` from `_PUBLIC_PATHS` so it requires the key, or gate the route behind `settings.alexa_skill_id` matching `body["session"]["application"]["applicationId"]`. The skill-ID check is ~5 lines and stops casual abuse, though it's not a substitute for signature verification.

### 1.4 — De-silence the exception handlers `[M, reliability]`

**Why it bites you:** This is the #1 source of "it broke and I have no idea why." I found 15+ `except Exception: pass` / `continue` blocks — in keychain cache-clears, MCP cleanup, briefing prefetch, settings handlers. A bad credential or a dead tool fails *silently*; you learn about it from NOVA quietly not doing the thing.

**The fix:** You don't delete them — you make them *speak*. Convert every bare swallow to:
```python
except Exception as e:
    logger.warning("kc cache clear failed", exc_info=True)  # was: pass
```
Then triage: the handful that are guarding genuinely-optional work (briefing brain lookup) stay as logged warnings; the ones in credential/save paths should arguably re-raise so the API returns a real error instead of a silent `{"status": "saved"}` when it didn't save. Concrete offenders to start with: the `at._API_KEY = None` clears in `routes_settings.py`, the Microsoft token clear, and the MCP disconnect handler.

### 1.5 — Stop rebuilding the agent executor every 60 seconds `[S, reliability + cost]`

**Why it bites you:** `_get_executor()` rebuilds the entire LangChain agent and re-reads all MCP tools once a minute, purely to refresh the date in the prompt. That's 1,440 full rebuilds/day, each a chance for an MCP read to hang or throw — and it makes latency spiky.

**The fix:** Build the executor **once**. Inject the current time at invoke time instead of baking it into a per-minute prompt — either as part of the input string or via a small prompt variable. The executor itself has no reason to expire.

### 1.6 — Confirm the GCP service-account key is gitignored `[S, security-critical]`

**Why it bites you:** `client.py` defaults to `secrets/gcp-service-account.json` inside the project tree. If that ever gets committed, it's not a NOVA leak — it's a `hypernovalabs-sa` GCP compromise.

**The fix:** `git log --all --full-history -- "*gcp-service-account.json" "secrets/*"` to confirm it was never committed, and verify `.gitignore` covers `secrets/`, `.env`, `*.json` creds, and `.agilitytask/`. If it *was* ever committed, rotate the key — history rewriting isn't enough once it's pushed.

---

## Week 2 — Make it survive restarts and surface its own health

This is the core of "it breaks on me." Right now a launchd restart wipes every conversation, the Vertex sessions, and all caches. On a 16GB box running Whisper + the agent, restarts happen.

### 2.1 — Persist conversation sessions `[L, reliability]`

**Why it bites you:** `session.py` is a 17-line in-memory dict of `ConversationBufferWindowMemory(k=10)`. Restart = every conversation forgets itself mid-thread. To you that feels like NOVA randomly "getting dumber."

**The fix (single-user appropriate):** You already have SQLite wired up for the task system (`app/tasks/store.py`). Reuse that engine — don't add Redis for a one-user box. Back the session memory with a tiny `sessions` table: `(session_id, role, content, ts)`, load the last `k` on access, append on each turn. LangChain has `SQLChatMessageHistory` that drops in with minimal glue. Keep the in-memory dict as a write-through cache so you don't hit disk every turn.

### 2.2 — Add a real `/health` that tells you what's actually up `[M, reliability]`

**Why it bites you:** When something's off, you have no fast way to see *which* dependency died — Gemini, Whisper, MCP, Vertex, the task runner, Outlook auth. You restart blind.

**The fix:** Expand the health route to probe each subsystem and return per-component status: LLM reachable, Whisper model loaded, MCP servers connected (you already have `get_mcp_status()`), Vertex engine cache populated (`get_cache_stats()` exists), task runner alive, task DB writable. Return `200` only if the criticals are green, `503` otherwise. Then a single `curl /health | jq` tells you the story instead of log archaeology.

### 2.3 — Structured logging you can actually grep `[M, reliability]`

**Why it bites you:** `logging.basicConfig` with default format means when a task fails at 2am you're reconstructing causality from unstructured lines with no request/session correlation.

**The fix:** Switch to a structured formatter (JSON lines, or at minimum a consistent format with `session_id` / `task_id` / `client_id` fields). Add a request-ID middleware that stamps each request and threads the ID through to tool calls and task logs. You don't need a full observability stack for one user — you need to be able to answer "what happened in *that* conversation" in one `grep`. Rotate logs to a file via launchd so they survive and don't fill the disk.

### 2.4 — Fix `client_id` propagation with `contextvars` `[M, correctness]`

**Why it bites you:** The orchestrator stashes `client_id` in `threading.local`, but the task runner executes tools through a `ThreadPoolExecutor` / `run_in_executor`. Thread-local state does **not** reliably cross that boundary, so background-task tool calls can silently see `"default"` instead of the real client. Even single-user, this corrupts the Vertex session-pool keying.

**The fix:** Replace `threading.local()` with `contextvars.ContextVar`. It propagates correctly through `async` and, with `contextvars.copy_context()`, through executor submissions. Small change, removes a whole class of "why did it use the wrong session" weirdness.

---

## Week 3 — Stop the agent/task layer from lying about success

These are the reliability bugs specific to your orchestration layer — the places where NOVA reports success it didn't achieve.

### 3.1 — Make the quality check fail *closed*, not open `[S, reliability]`

**Why it bites you:** In `agent.py`, `_assess_quality` returns `"complete"` from its `except` block. When the check itself fails, NOVA tells you the answer was good without ever checking. Combined with the keyword-matching `_is_valid_response`, your quality gate is mostly decorative.

**The fix:** On check failure, return `"unknown"` and *surface that* in the result ("couldn't verify completeness") rather than asserting completeness. And lean less on the brittle Spanish/English phrase list — a short structured LLM judgment ("did this answer the question? yes/no/partial + why") is more robust than substring matching that flags any answer containing "no tengo información."

### 3.2 — Harden the Vertex SDK→REST→LLM fallback chain `[M, reliability]`

**Why it bites you:** `reasoning_engine_query` tries SDK, falls to REST, falls to an error format — many independent failure points, and a stale pooled session can make *both* SDK and REST fail with the same expiry error before anyone evicts it.

**The fix:** On a session-expiry / not-found error, **evict the pooled session and retry once with a fresh one** before declaring failure (you have `_evict_session` already — wire it into the error path). Add a short timeout to the SDK call so a hung control-plane request can't stall the whole turn. Log *which* layer ultimately served the response so you can see when SDK is silently always-failing-to-REST.

### 3.3 — Per-client rate limiting (lightweight) `[M, reliability]`

**Why it bites you:** Even single-user, a runaway frontend retry loop or a stuck Alexa device can hammer `/chat` and burn your Gemini quota and both task workers, taking NOVA down for *you*. This is a reliability item, not just a multi-client one.

**The fix:** A simple in-process token-bucket per client_id (or per IP) on `/chat`, `/voice`, and task creation. `slowapi` drops into FastAPI cleanly, or hand-roll ~30 lines since you don't need distributed limits. Cap concurrent task submissions too, so a burst can't queue 50 tasks against 2 workers.

### 3.4 — Search provider fallback `[S, reliability]`

**Why it bites you:** Brave is the only search backend. Brave has an outage → the research worker is dead and you don't know why until you read logs.

**The fix:** Wrap `web_search` so a Brave failure falls back to a second provider (DuckDuckGo's API is keyless and fine as a backstop) and *logs* the downgrade. Even a degraded result beats a silent dead worker.

---

## A minimal guardrails module (optional, fits the single-user goal)

The empty `app/guardrails/__init__.py` doesn't need the full RBAC system I'd build for multi-tenant. For a single trusted user, give it exactly two jobs:

1. **Audit log of side-effecting tool calls.** Before any tool that sends/changes the outside world runs (`send_email`, `send_outlook_email`, `create_calendar_event`, `control_device`, `create_task`), append a line to an audit log: timestamp, tool, args summary, session. This is your "what did NOVA actually do today" record — invaluable when it does something unexpected.
2. **A confirmation gate for the destructive ones.** Optionally require a confirmation step before `send_email` / `control_device` actually fire, so a hallucinated tool call can't silently email a client. For voice-first UX you might gate only the highest-stakes tools.

That's ~100 lines and it directly serves reliability (you can see and constrain what the agent does), without the weight of a permissions system you don't need yet.

---

## What I deliberately left out (and when to revisit)

| Deferred | Why it's safe to skip now | Revisit when |
|---|---|---|
| User accounts / multi-tenant | You're single-user | You onboard a second real person |
| Vector-search brain | File-based recall is fine at your scale | Brain exceeds a few hundred notes |
| Frontend rewrite / TypeScript | Vanilla JS works; audio is patched-but-stable | You add a second client surface |
| Redis | SQLite covers one user fine | You need cross-process shared state |
| Full Alexa SDK | Skill-ID check is enough if Alexa is light-use | Alexa becomes a primary surface |

---

## Suggested order if a week slips

If you only get through Week 1, you've closed the internet-facing holes and silenced the worst debugging black-hole — that alone makes NOVA meaningfully more trustworthy. If you get through Week 2, restarts stop costing you conversations, which is the single biggest "it breaks on me" complaint. Week 3 is polish on the orchestration honesty. **Do them in order** — each week's foundation makes the next cheaper.
