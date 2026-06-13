"""Tests for durable conversation persistence (Week 2.1).

NOVA_HOME / cache isolation is handled by the autouse _patch_settings fixture.
"""

from app.agent import session, session_store


class TestSessionPersistence:
    def test_should_SurviveRestart_when_TurnsPersisted(self):
        session.persist_turn("s1", "me llamo Emeldo", "Encantado")
        session.persist_turn("s1", "que dije?", "Dijiste Emeldo")

        # Simulate a process restart: drop the in-memory cache + DB connection.
        session._sessions.clear()
        session_store._conn.close()
        session_store._conn = None

        mem = session.get_memory("s1")
        contents = [m.content for m in mem.chat_memory.messages]
        assert len(contents) == 4
        assert any("Emeldo" in c for c in contents)

    def test_should_HydrateInOrder_when_Loaded(self):
        session.persist_turn("s2", "first-q", "first-a")
        session.persist_turn("s2", "second-q", "second-a")
        session._sessions.clear()

        mem = session.get_memory("s2")
        roles = [type(m).__name__ for m in mem.chat_memory.messages]
        contents = [m.content for m in mem.chat_memory.messages]
        assert roles == ["HumanMessage", "AIMessage", "HumanMessage", "AIMessage"]
        assert contents[0] == "first-q" and contents[-1] == "second-a"

    def test_should_IsolateSessions_when_DifferentIds(self):
        session.persist_turn("a", "hi a", "yo a")
        session._sessions.clear()
        assert len(session.get_memory("b").chat_memory.messages) == 0

    def test_should_LimitToWindow_when_ManyTurns(self):
        for i in range(50):
            session.persist_turn("big", f"q{i}", f"a{i}")
        session._sessions.clear()
        # Loads at most 2*window turns (2*10 messages each = 40), newest retained.
        msgs = session.get_memory("big").chat_memory.messages
        assert len(msgs) <= session._WINDOW * 2
        assert msgs[-1].content == "a49"

    def test_should_RemoveHistory_when_Cleared(self):
        session.persist_turn("c", "secret", "ok")
        session.clear_session("c")
        session._sessions.clear()
        assert len(session.get_memory("c").chat_memory.messages) == 0
