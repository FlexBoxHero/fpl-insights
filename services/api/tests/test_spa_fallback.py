from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import build_server, spa_response


def _write_spa(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>spa-shell</html>", encoding="utf-8")
    (tmp_path / "main.js").write_text("console.log(1)", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "logo.svg").write_text("<svg></svg>", encoding="utf-8")
    return tmp_path


@pytest.fixture
def spa_client(tmp_path: Path) -> TestClient:
    spa = _write_spa(tmp_path)
    with patch("app.main.SPA_DIR", spa):
        yield TestClient(build_server())


def test_angular_route_serves_index(spa_client: TestClient) -> None:
    response = spa_client.get("/team")
    assert response.status_code == 200
    assert "spa-shell" in response.text
    assert "text/html" in response.headers["content-type"]


def test_nested_angular_route_serves_index(spa_client: TestClient) -> None:
    response = spa_client.get("/players")
    assert response.status_code == 200
    assert "spa-shell" in response.text


def test_existing_asset_is_served(spa_client: TestClient) -> None:
    response = spa_client.get("/main.js")
    assert response.status_code == 200
    assert "console.log(1)" in response.text


def test_nested_asset_is_served(spa_client: TestClient) -> None:
    response = spa_client.get("/assets/logo.svg")
    assert response.status_code == 200
    assert "<svg" in response.text


def test_root_serves_index(spa_client: TestClient) -> None:
    response = spa_client.get("/")
    assert response.status_code == 200
    assert "spa-shell" in response.text


def test_health_is_not_captured_by_spa(spa_client: TestClient) -> None:
    response = spa_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_mount_is_not_captured_by_spa(spa_client: TestClient) -> None:
    response = spa_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_path_escape_is_rejected(tmp_path: Path) -> None:
    spa = _write_spa(tmp_path)
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("leaked", encoding="utf-8")
    with patch("app.main.SPA_DIR", spa):
        with pytest.raises(HTTPException) as exc:
            spa_response("../" + secret.name)
        assert exc.value.status_code == 404
