from dataclasses import dataclass

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.api_keys import Role, generate_key, hash_key
from app.core.auth import Principal, get_api_key_repo, require_role
from app.core.errors import register_error_handlers


@dataclass
class Rec:
    id: str
    role: str
    enabled: bool = True


KEYS = {
    "user-key": Rec("dev-user", "nguoi_dung"),
    "editor-key": Rec("dev-editor", "bien_tap_vien"),
    "admin-key": Rec("dev-admin", "quan_tri"),
    "disabled-key": Rec("dev-old", "quan_tri", enabled=False),
}


class FakeRepo:
    async def find_by_hash(self, key_hash: str) -> Rec | None:
        for raw, rec in KEYS.items():
            if hash_key(raw) == key_hash:
                return rec
        return None


def make_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.dependency_overrides[get_api_key_repo] = lambda: FakeRepo()

    @app.get("/editor-only")
    async def editor_only(p: Principal = Depends(require_role(Role.BIEN_TAP_VIEN))) -> dict:
        return {"id": p.id, "role": p.role.value}

    return TestClient(app)


client = make_client()


def test_missing_key_401() -> None:
    r = client.get("/editor-only")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("key", ["wrong", "disabled-key"])
def test_invalid_or_disabled_key_401(key: str) -> None:
    assert client.get("/editor-only", headers={"X-API-Key": key}).status_code == 401


def test_lower_role_403() -> None:
    r = client.get("/editor-only", headers={"X-API-Key": "user-key"})
    assert r.status_code == 403
    assert r.json()["error"]["details"] == {"role": "nguoi_dung", "required": "bien_tap_vien"}


@pytest.mark.parametrize(
    ("key", "role"), [("editor-key", "bien_tap_vien"), ("admin-key", "quan_tri")]
)
def test_same_or_higher_role_ok(key: str, role: str) -> None:
    r = client.get("/editor-only", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json()["role"] == role


def test_generated_keys_unique_and_hash_stable() -> None:
    a, b = generate_key(), generate_key()
    assert a != b and a.startswith("lg_")
    assert hash_key(a) == hash_key(a) and len(hash_key(a)) == 64
