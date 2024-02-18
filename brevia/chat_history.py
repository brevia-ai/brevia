"""Chat history table & utilities"""
from typing import List
import logging
from datetime import datetime, time
from langchain_community.vectorstores.pgembedding import BaseModel, CollectionStore
from pydantic import BaseModel as PydanticModel
import sqlalchemy
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, Query, Session
from sqlalchemy.sql.expression import BinaryExpression
from brevia.connection import db_connection
from brevia.models import load_embeddings
from brevia.settings import get_settings
from brevia.utilities.json_api import query_data_pagination
from brevia.utilities.uuid import is_valid_uuid


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
    user_evaluation = sqlalchemy.Column(
        sqlalchemy.BOOLEAN(),
        nullable=True,
    )
    user_feedback = sqlalchemy.Column(sqlalchemy.String)
    chat_source = sqlalchemy.Column(sqlalchemy.String)


def history(chat_history: list, session: str = None):
    """ Load chat history from input or from DB """
    if len(chat_history) > 0:
        return [(x["query"], x["answer"]) for x in chat_history]

    if not is_valid_uuid(session) or get_settings().qa_no_chat_history:
        return []

    return history_from_db(session)


def is_related(chat_history: list, question: str):
    """
    Determine whether a question is related to a sequence of sentences.
    Use sentence and question embeddings to calculate the product
    scale between the vectors (in this case = similarity) and compare it
    with a threshold specified by environment variables.
    """
    embeddings = load_embeddings()
    q_e = embeddings.embed_query(question)
    h_e = embeddings.embed_query(
        ''.join([sentence for tuple in chat_history for sentence in tuple])
    )
    sim = dot_product(q_e, h_e)
    logging.getLogger(__name__).info("similarity: %s", sim)
    threshold = get_settings().qa_followup_sim_threshold
    return sim >= threshold


def dot_product(v1_list, v2_list):
    """
    Calculate the scalar product between two vectors (similarity).
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
    chat_source: str | None = None,
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
            chat_source=chat_source,
        )
        session.expire_on_commit = False
        session.add(chat_history_store)
        session.commit()

        return chat_history_store


class ChatHistoryFilter(PydanticModel):
    """ Chat history filter """
    min_date: str | None = None
    max_date: str | None = None
    collection: str | None = None
    session_id: str | None = None
    page: int = 1
    page_size: int = 50


def get_history(filter: ChatHistoryFilter) -> dict:
    """
        Read chat history with optional filters
        using pagination data in response
    """
    max_date = datetime.now()
    if filter.max_date is not None:
        max_date = datetime.strptime(filter.max_date, '%Y-%m-%d')
    max_date = datetime.combine(max_date, time.max)

    min_date = datetime.fromtimestamp(0)
    if filter.min_date is not None:
        min_date = datetime.strptime(filter.min_date, '%Y-%m-%d')
    min_date = datetime.combine(min_date, time.min)
    filter_collection = CollectionStore.name == filter.collection
    if filter.collection is None:
        filter_collection = CollectionStore.name is not None
    filter_session_id = sqlalchemy.text('1 = 1')  # (default) always true expression
    if filter.session_id and is_valid_uuid(filter.session_id):
        filter_session_id = ChatHistoryStore.session_id == filter.session_id

    with Session(db_connection()) as session:
        query = get_history_query(
            session=session,
            filter_min_date=ChatHistoryStore.created >= min_date,
            filter_max_date=ChatHistoryStore.created <= max_date,
            filter_collection=filter_collection,
            filter_session_id=filter_session_id,
        )
        result = query_data_pagination(
            query=query,
            page=filter.page,
            page_size=filter.page_size
        )
        session.close()

        return result


def get_history_query(
    session: Session,
    filter_min_date: BinaryExpression,
    filter_max_date: BinaryExpression,
    filter_collection: BinaryExpression,
    filter_session_id: BinaryExpression,
) -> Query:
    """Return get history query"""
    return (
        session.query(
            ChatHistoryStore.uuid,
            ChatHistoryStore.question,
            ChatHistoryStore.answer,
            ChatHistoryStore.session_id,
            ChatHistoryStore.cmetadata,
            ChatHistoryStore.created,
            CollectionStore.name.label('collection'),
            ChatHistoryStore.user_evaluation,
            ChatHistoryStore.user_feedback,
            ChatHistoryStore.chat_source,
        )
        .join(
            CollectionStore,
            CollectionStore.uuid == ChatHistoryStore.collection_id
        )
        .filter(filter_min_date, filter_max_date, filter_collection, filter_session_id)
        .order_by(sqlalchemy.desc(ChatHistoryStore.created))
    )


def history_evaluation(
    history_id: str,
    user_evaluation: bool,
    user_feedback: str | None = None,
) -> bool:
    """
        Update evaluation of single history item.
        Return false if history item is not found and true upon success.
    """
    with Session(db_connection()) as session:
        chat_history = session.get(ChatHistoryStore, history_id)
        if chat_history is None:
            return False
        chat_history.user_evaluation = user_evaluation
        chat_history.user_feedback = user_feedback
        session.add(chat_history)
        session.commit()

    return True
