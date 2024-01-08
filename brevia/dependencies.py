"""FastAPI endpoints dependencies"""
import shutil
from pathlib import Path
import tempfile
from jose import JWTError
from langchain_community.vectorstores.pgembedding import CollectionStore
from fastapi import HTTPException, status, Header, Depends, UploadFile
from fastapi.security import OAuth2PasswordBearer
from brevia import collections, tokens
from brevia.settings import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')  # use token authentication


def get_dependencies(json_content_type: bool = True) -> list[Depends]:
    """Get endpoint dependencies"""
    deps = []
    # add authorization header check only if access tokens are defined
    if get_settings().tokens_secret:
        deps.append(Depends(token_auth))

    if json_content_type:
        deps.append(Depends(application_json))

    return deps


def application_json(content_type: str = Header(...)):
    """Require request MIME-type to be application/json"""

    if content_type != "application/json":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported media type: {content_type}."
            " It must be application/json",
        )


def token_auth(token: str = Depends(oauth2_scheme)):
    """Check authorization header bearer token"""
    try:
        tokens.verify_token(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid token',
        ) from exc


def check_collection_name(name: str) -> CollectionStore:
    """Raise a 404 response if a collection name does not exist"""
    collection = collections.single_collection_by_name(name)
    if not collection:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Collection name '{name}' was not found",
        )

    return collection


def check_collection_uuid(uuid: str):
    """Raise a 404 response if a collection uuid does not exist"""
    if not collections.collection_exists(uuid=uuid):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Collection id '{uuid}' was not found",
        )


def check_collection_name_absent(name: str):
    """Raise a 409 conflict if a collection name already exists"""
    if collections.collection_name_exists(name=name):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Collection '{name}' exists",
        )


def save_upload_file_tmp(upload_file: UploadFile) -> str:
    """ Save uploaded file to temp file, return path """
    try:
        suffix = Path(upload_file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(upload_file.file, tmp)
    finally:
        upload_file.file.close()

    return str(Path(tmp.name))
