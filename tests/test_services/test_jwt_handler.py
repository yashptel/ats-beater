import pytest
from app.services.auth.jwt_handler import create_access_token, verify_token
from app.exceptions import AuthenticationError


def test_create_and_verify_token():
    token = create_access_token("user-123", "user@example.com")
    payload = verify_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"


def test_verify_invalid_token():
    with pytest.raises(AuthenticationError, match="token_invalid"):
        verify_token("invalid-token-string")
