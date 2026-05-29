from langchain.memory import ConversationBufferWindowMemory

_sessions: dict[str, ConversationBufferWindowMemory] = {}


def get_memory(session_id: str) -> ConversationBufferWindowMemory:
    if session_id not in _sessions:
        _sessions[session_id] = ConversationBufferWindowMemory(
            k=10,
            memory_key="chat_history",
            return_messages=True,
        )
    return _sessions[session_id]


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
