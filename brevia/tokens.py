"""JWT Utility methods"""
from os import environ
import click
from dotenv import load_dotenv
from jose import jwt, JWTError
from datetime import datetime, timedelta

ALGORITHM = 'HS256'


@click.command()
@click.option("-u", "--user", default="brevia", help="Token user name")
@click.option("-d", "--duration", default=15, help="Token duration in minutes")
def create_access_token(user: str, duration: int):
    """Create an access token """
    load_dotenv()
    to_encode = {'user': user}
    # expire time of the token
    expire = datetime.utcnow() + timedelta(minutes=duration)
    to_encode.update({'exp': expire})
    secret = environ.get('TOKENS_SECRET')
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    print(encoded_jwt)


def verify_token(token: str):
    # try to decode the token, it will
    # raise a JWTError if the token is not correct
    secret = environ.get('TOKENS_SECRET')
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    # basic check: presence of `user` key, must be a non empty string
    if 'user' not in payload:
        raise JWTError('Bad payload format')
    user = payload['user']
    if type(user) != str or len(user.strip()) == 0:
        raise JWTError('Bad payload format')
    # further check: user must one of `TOKENS_USERS` env var (if set)
    valid_users = environ.get('TOKENS_USERS')
    if not valid_users:
        return
    if user not in valid_users.split(','):
        raise JWTError('Bad payload format')
