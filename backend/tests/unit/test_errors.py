from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError, register_error_handlers
from app.core.logging import request_id_middleware
from app.core.pagination import Page, PageParams, page_params


class Body(BaseModel):
    n: int


def make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)

    @app.get("/app-error")
    async def app_error() -> None:
        raise AppError(
            "UNIT_NOT_FOUND",
            "Không tìm thấy điều khoản 123/2020/NĐ-CP:Đ3:K99",
            status_code=404,
            details={"unit_id": "123/2020/NĐ-CP:Đ3:K99"},
        )

    @app.post("/validate")
    async def validate(body: Body) -> dict[str, int]:
        return {"n": body.n}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/items")
    async def items(p: Annotated[PageParams, Depends(page_params)]) -> Page[int]:
        data = list(range(45))
        return Page.of(data[p.offset : p.offset + p.limit], p, total=len(data))

    return app


client = TestClient(make_app(), raise_server_exceptions=False)


def test_app_error_format() -> None:
    r = client.get("/app-error")
    assert r.status_code == 404
    assert r.json() == {
        "error": {
            "code": "UNIT_NOT_FOUND",
            "message": "Không tìm thấy điều khoản 123/2020/NĐ-CP:Đ3:K99",
            "details": {"unit_id": "123/2020/NĐ-CP:Đ3:K99"},
        }
    }


def test_validation_error_format() -> None:
    r = client.post("/validate", json={"n": "abc"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["errors"][0]["loc"] == ["body", "n"]


def test_not_found_route_format() -> None:
    r = client.get("/khong-co")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_unhandled_error_hides_detail() -> None:
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in r.text


def test_request_id_generated_and_echoed() -> None:
    r = client.get("/app-error")
    assert len(r.headers["X-Request-ID"]) == 32
    r2 = client.get("/app-error", headers={"X-Request-ID": "abc-123"})
    assert r2.headers["X-Request-ID"] == "abc-123"
    r3 = client.get("/app-error", headers={"X-Request-ID": "bad id with spaces"})
    assert r3.headers["X-Request-ID"] != "bad id with spaces"


def test_pagination() -> None:
    r = client.get("/items", params={"page": 3, "page_size": 20})
    assert r.json() == {"items": list(range(40, 45)), "page": 3, "page_size": 20, "total": 45}
    assert client.get("/items", params={"page": 0}).status_code == 422
    assert client.get("/items", params={"page_size": 101}).status_code == 422
