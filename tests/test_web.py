import pytest

from skillsift.web import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings)
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["skills"] > 0


def test_dashboard_is_empty_at_first(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Nothing tracked yet" in response.data


def test_match_form_renders(client):
    assert client.get("/match").status_code == 200


def test_match_scores_and_saves(client, cv_text, jd_text):
    response = client.post(
        "/match",
        data={"cv": cv_text, "jd": jd_text, "title": "MLE", "company": "Acme", "save": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"MLE" in response.data
    assert b"Missing" in response.data
    assert b"Nothing tracked yet" not in client.get("/").data


def test_match_rejects_empty_input(client):
    response = client.post("/match", data={"cv": "", "jd": ""})
    assert response.status_code == 400
    assert b"Paste your CV" in response.data


def test_api_match_returns_json(client, cv_text, jd_text):
    response = client.post("/api/match", json={"cv": cv_text, "jd": jd_text, "title": "MLE"})
    assert response.status_code == 200
    body = response.json
    assert body["title"] == "MLE"
    assert "Python" in body["matched"]
    assert isinstance(body["missing_required"], list)


def test_api_match_requires_both_documents(client):
    response = client.post("/api/match", json={"cv": "Python"})
    assert response.status_code == 400
    assert "required" in response.json["error"]


def test_api_match_rejects_oversized_payloads(client):
    big = "python " * 40_000
    assert client.post("/api/match", json={"cv": big, "jd": big}).status_code == 413


def test_unknown_posting_is_404(client):
    assert client.get("/postings/999").status_code == 404


def test_status_can_be_updated_from_the_web(client, cv_text, jd_text):
    client.post("/match", data={"cv": cv_text, "jd": jd_text, "title": "MLE", "save": "1"})
    response = client.post(
        "/postings/1/status", data={"status": "interview", "notes": "call booked"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"call booked" in response.data


def test_bad_status_is_rejected(client, cv_text, jd_text):
    client.post("/match", data={"cv": cv_text, "jd": jd_text, "title": "MLE", "save": "1"})
    assert client.post("/postings/1/status", data={"status": "ghosted"}).status_code == 400
