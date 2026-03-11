"""
tests/test_api.py
~~~~~~~~~~~~~~~~~
Integration tests for the HTTP API.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentic_codebase_reader.api.app import create_app


@pytest.fixture()
def client() -> TestClient:
    """Return a synchronous test client for the FastAPI app."""
    return TestClient(create_app())


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_version(self, client: TestClient) -> None:
        data = response = client.get("/health").json()
        assert "version" in data


class TestAnalyzeEndpoint:
    @pytest.mark.xfail(reason="Not yet implemented")
    def test_analyze_valid_url(self, client: TestClient) -> None:
        """POST /analyze with a valid URL should return 200 and a repo_name."""
        raise NotImplementedError

    def test_analyze_invalid_url_returns_422(self, client: TestClient) -> None:
        """POST /analyze with a non-URL string should return 422."""
        response = client.post("/analyze", json={"repo_url": "not-a-url"})
        assert response.status_code == 422


class TestDownloadEndpoint:
    @pytest.mark.xfail(reason="Not yet implemented")
    def test_download_existing_repo(self, client: TestClient) -> None:
        """GET /download/<name> should return a Markdown file."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_download_missing_repo_returns_404(self, client: TestClient) -> None:
        """GET /download/<name> for unknown repo should return 404."""
        raise NotImplementedError
