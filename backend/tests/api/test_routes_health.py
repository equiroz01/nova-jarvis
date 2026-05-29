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
        assert data["service"] == "jarvis-backend"

    def test_should_RejectPost_when_WrongMethod(self, client):
        resp = client.post("/health")
        assert resp.status_code == 405
