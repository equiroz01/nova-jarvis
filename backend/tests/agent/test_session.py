"""Tests for session memory management."""

from app.agent.session import _sessions, get_memory, clear_session


class TestGetMemory:
    def setup_method(self):
        _sessions.clear()

    def teardown_method(self):
        _sessions.clear()

    def test_should_CreateNewMemory_when_SessionIdIsNew(self):
        mem = get_memory("new-session")
        assert mem is not None
        assert "new-session" in _sessions

    def test_should_ReturnSameInstance_when_SessionIdAlreadyExists(self):
        mem1 = get_memory("s1")
        mem2 = get_memory("s1")
        assert mem1 is mem2

    def test_should_ReturnDifferentInstances_when_DifferentSessionIds(self):
        mem1 = get_memory("s1")
        mem2 = get_memory("s2")
        assert mem1 is not mem2

    def test_should_HaveWindowSizeOf10_when_Created(self):
        mem = get_memory("s1")
        assert mem.k == 10

    def test_should_ReturnMessages_when_MemoryKeyIsCorrect(self):
        mem = get_memory("s1")
        assert mem.memory_key == "chat_history"
        assert mem.return_messages is True

    def test_should_IsolateSessions_when_MessagesAddedToOne(self):
        mem1 = get_memory("s1")
        mem2 = get_memory("s2")
        mem1.chat_memory.add_user_message("Hello from s1")
        assert len(mem2.chat_memory.messages) == 0
        assert len(mem1.chat_memory.messages) == 1

    def test_should_HandleEmptyStringSessionId_when_Provided(self):
        mem = get_memory("")
        assert mem is not None
        assert "" in _sessions


class TestClearSession:
    def setup_method(self):
        _sessions.clear()

    def teardown_method(self):
        _sessions.clear()

    def test_should_RemoveSession_when_SessionExists(self):
        get_memory("s1")
        assert "s1" in _sessions
        clear_session("s1")
        assert "s1" not in _sessions

    def test_should_DoNothing_when_SessionDoesNotExist(self):
        clear_session("nonexistent")  # Must not raise

    def test_should_NotAffectOtherSessions_when_OneCleared(self):
        get_memory("s1")
        get_memory("s2")
        clear_session("s1")
        assert "s1" not in _sessions
        assert "s2" in _sessions

    def test_should_AllowRecreation_when_SessionWasCleared(self):
        mem_old = get_memory("s1")
        mem_old.chat_memory.add_user_message("old msg")
        clear_session("s1")
        mem_new = get_memory("s1")
        assert mem_new is not mem_old
        assert len(mem_new.chat_memory.messages) == 0
