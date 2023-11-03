"""Tokens module tests"""
from os import environ
import pytest
from brevia.tokens import create_token, verify_token, ALGORITHM
from jose import jwt, JWTError


def test_verify_token():
    """Test verify_token function"""
    environ['TOKENS_SECRET'] = 'secretsecretsecret'
    token = create_token(user='gustavo', duration=20)
    verify_token(token)

    environ['TOKENS_USERS'] = 'brevia'
    with pytest.raises(JWTError) as exc:
        verify_token(token)
    assert str(exc.value) == 'Bad payload format'


def test_bad_token():
    """Test verify_token failure"""
    environ['TOKENS_SECRET'] = 'secretsecretsecret'

    token = jwt.encode({'test': True}, environ['TOKENS_SECRET'], algorithm=ALGORITHM)
    with pytest.raises(JWTError) as exc:
        verify_token(token)
    assert str(exc.value) == 'Bad payload format'

    token = jwt.encode({'user': None}, environ['TOKENS_SECRET'], algorithm=ALGORITHM)
    with pytest.raises(JWTError) as exc:
        verify_token(token)
    assert str(exc.value) == 'Bad payload format'
