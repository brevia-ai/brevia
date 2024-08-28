"""Tokens module tests"""
import pytest
from jose import jwt, JWTError
from brevia.tokens import create_token, verify_token, ALGORITHM
from brevia.settings import get_settings


def test_verify_token():
    """Test verify_token function"""
    settings = get_settings()
    settings.tokens_secret = 'secretsecretsecret'
    token = create_token(user='gustavo', duration=20)
    verify_token(token)

    settings.tokens_users = 'brevia'
    with pytest.raises(JWTError) as exc:
        verify_token(token)
    assert str(exc.value) == 'Bad payload format'
    settings.tokens_secret = ''
    settings.tokens_users = ''


def test_bad_token():
    """Test verify_token failure"""
    settings = get_settings()
    settings.tokens_secret = 'secretsecretsecret'

    token = jwt.encode({'test': True}, settings.tokens_secret, algorithm=ALGORITHM)
    with pytest.raises(JWTError) as exc:
        verify_token(token)
    assert str(exc.value) == 'Bad payload format'

    token = jwt.encode({'user': None}, settings.tokens_secret, algorithm=ALGORITHM)
    with pytest.raises(JWTError) as exc:
        verify_token(token)
    assert str(exc.value) == 'Bad payload format'

    settings.tokens_secret = ''
