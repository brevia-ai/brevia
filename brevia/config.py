"""Config table & utilities"""
from fnmatch import fnmatch
from sqlalchemy import Column, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Session
from langchain_community.vectorstores.pgembedding import BaseModel
from brevia.connection import db_connection
from brevia.settings import Settings


class ConfigStore(BaseModel):
    # pylint: disable=too-few-public-methods,not-callable
    """ Config table """
    __tablename__ = "config"

    config_key = Column(String(), nullable=False, comment='Configuration name'),
    config_val = Column(String(), nullable=False, comment='Configuration value'),
    created = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    modified = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


def configurable_settings() -> list[str]:
    keys = Settings.model_fields.keys()
    excluded_keys = {"pg_vector*", "tokens_secret"}

    return [key for key in keys
            if not any(fnmatch(key, pattern) for pattern in excluded_keys)]


def read_conf() -> dict[str, str]:
    """ Read all config records """
    with Session(db_connection()) as session:
        query = session.query(ConfigStore.config_key, ConfigStore.config_val)
        items = {key: value for key, value in query.all()}
        # Filter out non-configurable settings
        return {key: value
                for key, value in items.items() if key in configurable_settings()}


def update_conf(items: dict[str, str]) -> dict[str, str]:
    """ Update config records """
    # Filter out non-configurable settings
    items = {key: value for key, value in items.items() if key in configurable_settings()}
    with Session(db_connection()) as session:
        session.expire_on_commit = False
        query = session.query(ConfigStore.config_key, ConfigStore.config_val)
        current_conf = {u.config_key: u for u in query.all()}
        for key, value in items.items():
            if key not in current_conf:
                session.add(ConfigStore(config_key=key, config_val=value))
            elif current_conf[key].config_val != value:
                current_conf[key].config_val = value
                session.add(current_conf[key])
        for key in current_conf.keys():
            if key not in items:
                session.delete(current_conf[key])

        session.commit()

    return read_conf()
