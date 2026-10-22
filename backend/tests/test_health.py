def test_health_reports_mode(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["llm_mode"] == "offline"
