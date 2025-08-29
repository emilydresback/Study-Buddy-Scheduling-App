import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_route(client):
    """Test the home page loads successfully"""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Welcome" in response.data or b"<html" in response.data

def test_dashboard_route(client):
    """Test the dashboard page is reachable"""
    response = client.get('/dashboard')
    print("Status code:", response.status_code)
    print("Redirect target (if any):", response.headers.get('Location'))
    
    # Accept either 200 (OK) or 302 (redirect to login)
    assert response.status_code in (200, 302)

def test_nonexistent_route(client):
    """Test a route that doesn’t exist returns 404"""
    response = client.get('/not-a-real-page')
    assert response.status_code == 404