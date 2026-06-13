"""Tests for GET /health endpoint."""


class TestHealthEndpoint:
    def test_should_Return200_when_ServiceIsRunning(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_should_ReturnOkStatus_when_Called(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_should_ReturnServiceName_when_Called(self, client):
        data = client.get("/health").json()
        assert data["service"] == "nova-backend"

    def test_should_RejectPost_when_WrongMethod(self, client):
        resp = client.post("/health")
        assert resp.status_code == 405


class TestHealthDetailGating:
    """Detail must not leak to the internet (Week 2.2). The TestClient host is not
    a LAN IP, so it is trusted only when it carries a valid key."""

    def test_should_ReturnBareLiveness_when_Untrusted(self, client):
        # No key on the request and host is not LAN → bare liveness, no topology.
        resp = client.get("/health", headers={"cf-connecting-ip": "8.8.8.8"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "checks" not in body

    def test_should_ReturnFullDetail_when_ValidKey(self, client, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "nova_api_key", "k")
        resp = client.get("/health", headers={"authorization": "Bearer k"})
        data = resp.json()
        assert "checks" in data
        assert "llm" in data["checks"]
        assert "task_db" in data["checks"]
