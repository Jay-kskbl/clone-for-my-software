"""T06：密码哈希与登录令牌（纯函数，不需要数据库）。"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "unit-test-secret-not-used-anywhere-else-0123456789"
OTHER_SECRET = "another-unit-test-secret-0123456789-abcdefghijklmn"
USER_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")


# ---- 密码 ----


def test_hash_is_not_the_password_and_uses_argon2id():
    hashed = hash_password("correct horse battery")

    assert "correct horse battery" not in hashed
    assert hashed.startswith("$argon2id$")


def test_same_password_hashes_differently_each_time():
    # 每次随机加盐：两个用户用同一个密码，数据库里也看不出来
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_accepts_correct_and_rejects_wrong_password():
    hashed = hash_password("correct horse battery")

    assert verify_password("correct horse battery", hashed) is True
    assert verify_password("Correct horse battery", hashed) is False
    assert verify_password("", hashed) is False


@pytest.mark.parametrize("stored", ["", "plaintext-password", "$argon2id$broken"])
def test_verify_returns_false_for_malformed_stored_hash(stored):
    assert verify_password("anything", stored) is False


# ---- 令牌 ----


def test_token_round_trip():
    token = create_access_token(USER_ID, secret=SECRET, expires_in_seconds=60)

    assert decode_access_token(token, secret=SECRET) == USER_ID


def test_expired_token_rejected():
    long_ago = datetime.now(UTC) - timedelta(hours=2)
    token = create_access_token(USER_ID, secret=SECRET, expires_in_seconds=3600, now=long_ago)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_token_signed_with_other_secret_rejected():
    token = create_access_token(USER_ID, secret=OTHER_SECRET, expires_in_seconds=60)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_tampered_payload_rejected():
    token = create_access_token(USER_ID, secret=SECRET, expires_in_seconds=60)
    header, _payload, signature = token.split(".")
    other = create_access_token(uuid.uuid4(), secret=OTHER_SECRET, expires_in_seconds=60)
    forged = f"{header}.{other.split('.')[1]}.{signature}"

    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, secret=SECRET)


def test_unsigned_alg_none_token_rejected():
    exp = datetime.now(UTC) + timedelta(minutes=5)
    token = jwt.encode({"sub": str(USER_ID), "exp": exp}, key=None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


@pytest.mark.parametrize(
    "payload",
    [
        {"sub": str(USER_ID)},  # 没有过期时间
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},  # 没有用户
        {"sub": "not-a-uuid", "exp": datetime.now(UTC) + timedelta(minutes=5)},
    ],
    ids=["no-exp", "no-sub", "sub-not-uuid"],
)
def test_token_missing_required_claims_rejected(payload):
    token = jwt.encode(payload, SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_token_rejected(token):
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)
