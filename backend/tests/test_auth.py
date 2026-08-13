import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.auth import hash_password, verify_password, create_access_token, get_current_user, ALGORITHM
from app.models import User


def test_hash_password_and_verify_roundtrip():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_access_token_encodes_user_id():
    token = create_access_token(user_id=42)
    payload = jwt.decode(token, "test-secret-key-do-not-use-in-production", algorithms=[ALGORITHM])
    assert payload["sub"] == "42"


def test_get_current_user_returns_user_for_valid_token(db_session):
    user = User(email="a@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    db_session.flush()
    token = create_access_token(user_id=user.id)

    result = get_current_user(token=token, session=db_session)

    assert result.id == user.id


def test_get_current_user_rejects_malformed_token(db_session):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="not-a-real-token", session=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_expired_token(db_session):
    payload = {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
    expired_token = jwt.encode(payload, "test-secret-key-do-not-use-in-production", algorithm=ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=expired_token, session=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_token_for_deleted_user(db_session):
    token = create_access_token(user_id=999999)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token, session=db_session)
    assert exc_info.value.status_code == 401


def test_create_access_token_raises_without_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_access_token(user_id=1)
