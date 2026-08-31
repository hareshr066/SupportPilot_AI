import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.api.main import app
from app.database.session import get_db_session

def override_get_db_session():
    mock_db = MagicMock()
    mock_db.scalars.return_value.all.return_value = []
    mock_db.scalar.return_value = 0
    yield mock_db

app.dependency_overrides[get_db_session] = override_get_db_session

client = TestClient(app)

def test_list_evaluations_endpoint():
    response = client.get("/api/v1/evaluations")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "evaluations" in data
    assert isinstance(data["evaluations"], list)

def test_get_nonexistent_evaluation_details():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    
    def _override():
        yield mock_db
        
    app.dependency_overrides[get_db_session] = _override
    response = client.get("/api/v1/evaluations/eval_nonexistent_999")
    assert response.status_code == 404
