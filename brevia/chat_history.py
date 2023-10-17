"""Chat history table & utilities"""
from typing import List
import uuid
import logging
from datetime import datetime
from os import environ
from langchain.vectorstores.pgvector import BaseModel
from langchain.vectorstores._pgvector_data_models import CollectionStore
import sqlalchemy
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, Query, Session
from sqlalchemy.sql.expression import BinaryExpression
from brevia.connection import db_connection
from brevia.index import get_embeddings


class ChatHistoryStore(BaseModel):
    # pylint: disable=too-few-public-methods
    """ Chat History table """
    __tablename__ = "chat_history"

    session_id = sqlalchemy.Column(UUID(as_uuid=True))
    collection_id: Mapped[UUID] = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(
            f"{CollectionStore.__tablename__}.uuid",
            ondelete="CASCADE",
        ),
    )
    question = sqlalchemy.Column(sqlalchemy.String)
    answer = sqlalchemy.Column(sqlalchemy.String)
    # pylint: disable=not-callable
    created = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=False),
        nullable=False,
        server_default=sqlalchemy.sql.func.now()
    )
    cmetadata = sqlalchemy.Column(JSON, nullable=True)


def history(chat_history: list, session: str = None):
    """ Load chat history from input or from DB """
    if len(chat_history) > 0:
        return [(x["query"], x["answer"]) for x in chat_history]

    if not is_valid_uuid(session) or bool(environ.get('QA_NO_CHAT_HISTORY')):
        return []

    return history_from_db(session)


def is_related(chat_history: list, question: str):
    """
    Determina se una domanda è correlata a una sequenza di frasi.
    Utilizza gli embedding delle frasi e della domanda per calcolare il prodotto
    scalare tra i vettori (in questo caso = similarity) e confrontarlo
    con una soglia specificata dalle variabili d'ambiente.
    """
    embeddings = get_embeddings()
    q_e = embeddings.embed_query(question)
    h_e = embeddings.embed_query(
        ''.join([sentence for tuple in chat_history for sentence in tuple])
    )
    sim = dot_product(q_e, h_e)
    logging.getLogger(__name__).info("similarity: %s", sim)
    threshold = float(environ.get('QA_FOLLOWUP_SIM_THRESHOLD', False))
    return sim >= threshold


def dot_product(v1_list, v2_list):
    """
    Calcola il prodotto scalare tra due vettori (similarity).
    """
    return sum(x * y for x, y in zip(v1_list, v2_list))


def history_from_db(session_id: str) -> List[tuple[str, str]]:
    """ Load chat history from DB """
    connection = db_connection()

    filter_by = ChatHistoryStore.session_id == session_id
    with Session(connection) as session:
        results: List[ChatHistoryStore] = (
            session.query(ChatHistoryStore)
            .filter(filter_by)
            .order_by(sqlalchemy.desc(ChatHistoryStore.created))
            .limit(3)
            .all()
        )

    chat_hist = [(x.question, x.answer) for x in results]
    chat_hist.reverse()

    return chat_hist


def add_history(
    session_id: str,
    collection: str,
    question: str,
    answer: str,
    metadata: dict | None = None,
) -> (ChatHistoryStore | None):
    """Save chat history item to database """
    if not is_valid_uuid(session_id):
        return None

    with Session(db_connection()) as session:
        collection_store = CollectionStore.get_by_name(session, collection)
        if not collection_store:
            raise ValueError("Collection not found")
        chat_history_store = ChatHistoryStore(
            session_id=session_id,
            collection_id=collection_store.uuid,
            question=question,
            answer=answer,
            cmetadata=metadata,
        )
        session.expire_on_commit = False
        session.add(chat_history_store)
        session.commit()

        return chat_history_store


def is_valid_uuid(val) -> bool:
    """ Check UUID validity """
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError):
        return False


def get_history(
    max_date: str | None = None,
    collection: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
        Read chat history with optional date and collection filters
        using pagination data in response
    """
    max_date = datetime.now() if max_date is None else max_date
    filter_date = ChatHistoryStore.created <= max_date
    filter_collection = CollectionStore.name == collection
    if collection is None:
        filter_collection = CollectionStore.name is not None

    page = max(1, page)  # min page number is 1
    page_size = min(1000, page_size)  # max page size is 1000
    offset = (page - 1) * page_size

    with Session(db_connection()) as session:
        query = get_history_query(
            session=session,
            filter_date=filter_date,
            filter_collection=filter_collection,
        )
        count = query.count()
        results = [u._asdict() for u in query.offset(offset).limit(page_size).all()]
        pcount = int(count / page_size)
        pcount += 0 if (count % page_size) == 0 else 1
        session.close()

        return {
            'data': results,
            'meta': {
                'pagination': {
                    'count': count,
                    'page': page,
                    'page_count': pcount,
                    'page_items': len(results),
                    'page_size': page_size,
                },
            }
        }


def get_history_query(
    session: Session,
    filter_date: BinaryExpression,
    filter_collection: BinaryExpression,
) -> Query:
    """Return get history query"""
    return (
        session.query(
            ChatHistoryStore.question,
            ChatHistoryStore.answer,
            ChatHistoryStore.session_id,
            ChatHistoryStore.cmetadata,
            ChatHistoryStore.created,
            CollectionStore.name.label('collection'),
        )
        .join(
            CollectionStore,
            CollectionStore.uuid == ChatHistoryStore.collection_id
        )
        .filter(filter_date, filter_collection)
        .order_by(sqlalchemy.desc(ChatHistoryStore.created))
    )
