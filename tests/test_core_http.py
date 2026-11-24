# tests/test_core_http.py
"""基础设施层的 HTTP 契约测试：健康检查、统一错误体、request_id、422 形状。"""

from uuid import uuid4


def test_health_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_route_uses_unified_error_body(client):
    r = client.get(f"/no-such-path/{uuid4()}")
    assert r.status_code == 404
    assert r.json() == {"error_code": "NOT_FOUND", "message": "Not Found"}


def test_method_not_allowed_uses_unified_error_body(client):
    r = client.get("/auth/login/password")  # 该路径只支持 POST
    assert r.status_code == 405
    assert r.json()["error_code"] == "METHOD_NOT_ALLOWED"


def test_request_id_is_echoed(client):
    r = client.get("/", headers={"X-Request-ID": "trace-123"})
    assert r.headers["X-Request-ID"] == "trace-123"


def test_request_id_is_generated_when_absent(client):
    r = client.get("/")
    assert r.headers["X-Request-ID"]  # 32 位 hex


def test_validation_error_shape(client):
    """422 只回字段与原因，不回显原始输入（防密码泄漏）。"""
    r = client.post(
        "/auth/register/password",
        json={"account": "a", "password": "secret-should-not-echo"},
    )

    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert isinstance(body["errors"], list)
    assert any(e["field"] == "account" for e in body["errors"])
    assert "secret-should-not-echo" not in r.text


def test_openapi_schema_is_available(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/auth/users/me" in paths
    assert "/auth/users/me/identities" in paths
