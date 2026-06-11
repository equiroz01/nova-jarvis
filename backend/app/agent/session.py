from langchain.memory import ConversationBufferWindowMemory

from app.agent import session_store

_sessions: dict[str, ConversationBufferWindowMemory] = {}

_WINDOW = 10  # turns kept in the prompt window


def _new_memory() -> ConversationBufferWindowMemory:
    return ConversationBufferWindowMemory(
        k=_WINDOW,
        memory_key="chat_history",
        return_messages=True,
    )


def get_memory(session_id: str) -> ConversationBufferWindowMemory:
    """Return the live memory for a session, hydrating from disk on first access
    so a restart no longer wipes the conversation mid-thread."""
    if session_id not in _sessions:
        memory = _new_memory()
        # Hydrate from durable store (load a bit more than the window for context)
        for role, content in session_store.load_recent(session_id, _WINDOW * 2):
            if role == "user":
                memory.chat_memory.add_user_message(content)
            else:
                memory.chat_memory.add_ai_message(content)
        _sessions[session_id] = memory
    return _sessions[session_id]


def persist_turn(session_id: str, user_message: str, ai_response: str) -> None:
    """Append a completed turn to the durable store (write-through)."""
    session_store.append(session_id, "user", user_message)
    session_store.append(session_id, "ai", ai_response)


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    session_store.clear(session_id)
