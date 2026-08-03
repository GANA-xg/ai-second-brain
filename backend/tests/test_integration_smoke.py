"""Integration-style smoke tests for critical flows.

These tests exercise real application wiring through the FastAPI app and
the SQLAlchemy test database fixture, while keeping external services
stubbed so they stay reliable in CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


API_PREFIX = settings.API_V1_PREFIX
AUTH_PREFIX = f"{API_PREFIX}/auth"
FILES_PREFIX = f"{API_PREFIX}/files"


def test_token_lifecycle_round_trip(client: TestClient, registered_user):
    """Register, log in, refresh, and log out with real API endpoints."""
    email, password, _ = registered_user

    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    tokens = login.json()

    refresh = client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    refreshed = refresh.json()
    assert refreshed["access_token"] != tokens["access_token"]
    assert refreshed["refresh_token"] != tokens["refresh_token"]

    logout = client.post(
        f"{AUTH_PREFIX}/logout",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert logout.status_code == 200


def test_refresh_token_cannot_be_reused(client: TestClient, registered_user):
    """The refresh token rotation flow should reject token reuse."""
    email, password, _ = registered_user
    login = client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": email, "password": password},
    )
    refresh_token = login.json()["refresh_token"]

    first = client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": refresh_token},
    )
    assert first.status_code == 200

    second = client.post(
        f"{AUTH_PREFIX}/refresh",
        json={"refresh_token": refresh_token},
    )
    assert second.status_code == 401


def test_upload_pipeline_marks_document_ready_or_failed(client: TestClient, auth_headers):
    """Upload an actual file and verify the document lifecycle response."""
    with patch("app.services.processing_pipeline.DocumentPipeline") as mock_pipeline:
        pipeline = MagicMock()
        pipeline.process.side_effect = lambda db, doc: doc
        mock_pipeline.return_value = pipeline

        with patch("app.services.embedding_pipeline.EmbeddingPipeline") as mock_embedding:
            embedder = MagicMock()
            embedder.process.side_effect = lambda db, doc: doc
            mock_embedding.return_value = embedder

            response = client.post(
                f"{FILES_PREFIX}/upload",
                files={"file": ("note.txt", b"hello world")},
                headers=auth_headers,
            )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["original_filename"] == "note.txt"
    assert body["document"]["status"] in {"READY", "UPLOADED", "FAILED"}


def test_upload_rejects_unsupported_format(client: TestClient, auth_headers):
    """Unsupported uploads should be rejected early and cleanly."""
    response = client.post(
        f"{FILES_PREFIX}/upload",
        files={"file": ("bad.exe", b"binary")},
        headers=auth_headers,
    )
    assert response.status_code == 400
