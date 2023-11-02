"""JWT Utility methods"""
from os import environ
from datetime import datetime, timedelta
from jose import jwt, JWTError

ALGORITHM = 'HS256'


def create_token(user: str, duration: int) -> str:
    """Create an access token """
    # expire time of the token
    expire = datetime.utcnow() + timedelta(minutes=duration)
    to_encode = {
        'user': user,
        'exp': expire,
    }
    secret = environ.get('TOKENS_SECRET')

    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def verify_token(token: str):
    """
        Try to decode the token, it will
        raise a JWTError if the token is not correct
    """
    secret = environ.get('TOKENS_SECRET')
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    # basic check: presence of `user` key, must be a non empty string
    if 'user' not in payload:
        raise JWTError('Bad payload format')
    user = payload['user']
    if not isinstance(user, str) or len(user.strip()) == 0:
        raise JWTError('Bad payload format')
    # further check: user must one of `TOKENS_USERS` env var (if set)
    valid_users = environ.get('TOKENS_USERS')
    if not valid_users:
        return
    if user not in valid_users.split(','):
        raise JWTError('Bad payload format')
