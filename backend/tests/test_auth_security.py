from uuid import uuid4

import pytest

from app.auth.security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed_and_verifiable() -> None:
    password = "local-demo-password"

    encoded = hash_password(password)

    assert encoded != password
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_token_contains_valid_identity_and_role() -> None:
    user_id = uuid4()

    token = create_access_token(user_id, "Finance")
    claims = decode_access_token(token)

    assert claims.sub == user_id
    assert claims.role.value == "Finance"


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not-a-valid-token")
