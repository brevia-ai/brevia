"""Chat history table & utilities"""
from typing import List
import logging
from datetime import datetime, time
from langchain_community.vectorstores.pgembedding import BaseModel, CollectionStore
from pydantic import BaseModel as PydanticModel
import sqlalchemy
from sqlalchemy import func
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


def is_related(chat_history: list, question: str, embeddings: dict | None = None):
    """
    Determine whether a question is related to a sequence of sentences.
    Use sentence and question embeddings to calculate the product
    scale between the vectors (in this case = similarity) and compare it
    with a threshold specified by environment variables.
    """
    embeddings_engine = load_embeddings(embeddings)
    q_e = embeddings_engine.embed_query(question)
    h_e = embeddings_engine.embed_query(
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


def get_date_filter(date_str, type_str):
    """
    Parses a date string into a datetime object with combined time information.

    Args:
        date_str (str): A string representing a date in the format 'YYYY-MM-DD'.
            None if no specific date is provided.

        type_str (str): Indicates whether to create a maximum or minimum date filter.
            Valid values are 'max' or 'min'.
    """
    max_date = datetime.now()
    min_date = datetime.fromtimestamp(0)

    if date_str is not None:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
        if type_str == 'max':
            max_date = parsed_date
            return datetime.combine(max_date, time.max)
        min_date = parsed_date
        return datetime.combine(min_date, time.min)

    return max_date if type_str == 'max' else min_date


def get_collection_filter(collection_name):
    """
    Constructs a filter expression based on the collection name.
    """
    filter_collection = CollectionStore.name == collection_name
    if collection_name is None:
        filter_collection = CollectionStore.name is not None
    return filter_collection


def get_session_filter(session_id):
    """
    Constructs a filter expression based on the session ID.
    """
    filter_session_id = sqlalchemy.text('1 = 1')  # (default) always true expression
    if session_id and is_valid_uuid(session_id):
        filter_session_id = ChatHistoryStore.session_id == session_id

    return filter_session_id


def get_history(filter: ChatHistoryFilter) -> dict:  # pylint: disable=redefined-builtin
    """
    Read chat history with optional filters using pagination data in response.
    """

    min_date = get_date_filter(filter.min_date, 'min')
    max_date = get_date_filter(filter.max_date, 'max')
    filter_collection = get_collection_filter(filter.collection)
    filter_session_id = get_session_filter(filter.session_id)

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
        return result


def get_history_sessions(filter: ChatHistoryFilter) -> dict:
    # pylint: disable=redefined-builtin
    """
    Read chat history with optional filters using pagination data in response.
    """

    min_date = get_date_filter(filter.min_date, 'min')
    max_date = get_date_filter(filter.max_date, 'max')
    filter_collection = get_collection_filter(filter.collection)

    with Session(db_connection()) as session:
        query = get_history_sessions_query(
            session=session,
            filter_min_date=ChatHistoryStore.created >= min_date,
            filter_max_date=ChatHistoryStore.created <= max_date,
            filter_collection=filter_collection,
        )
        result = query_data_pagination(
            query=query,
            page=filter.page,
            page_size=filter.page_size
        )
        return result


def get_history_sessions_query(
    session: Session,
    filter_min_date: BinaryExpression,
    filter_max_date: BinaryExpression,
    filter_collection: BinaryExpression,
) -> Query:
    """
    Returns a SQLAlchemy query to fetch oldest chat history sessions
    for every session based on specified filters.
    """

    subquery = (
        session.query(
            ChatHistoryStore.session_id.label("session_id"),
            CollectionStore.name.label("collection"),
            # pylint: disable=not-callable
            func.min(ChatHistoryStore.created).label("min_created"),
        ).join(
            CollectionStore,
            CollectionStore.uuid == ChatHistoryStore.collection_id
        )
        .filter(filter_min_date, filter_max_date, filter_collection)
        .group_by(
            ChatHistoryStore.session_id,
            CollectionStore.name
        )
    ).subquery()

    query = (
        session.query(
            ChatHistoryStore.session_id,
            ChatHistoryStore.question,
            ChatHistoryStore.created,
            subquery.c.collection,
        )
        .join(subquery, ChatHistoryStore.session_id == subquery.c.session_id)
        .filter(ChatHistoryStore.created == subquery.c.min_created)
        .order_by(sqlalchemy.desc(ChatHistoryStore.created))
    )

    return query


def get_history_query(
    session: Session,
    filter_min_date: BinaryExpression,
    filter_max_date: BinaryExpression,
    filter_collection: BinaryExpression,
    filter_session_id: BinaryExpression,
) -> Query:
    """
    Constructs a SQLAlchemy query to retrieve chat history based on specified filters.
    """

    query = (
        session.query(
            ChatHistoryStore.uuid,
            ChatHistoryStore.question,
            ChatHistoryStore.answer,
            ChatHistoryStore.session_id,
            ChatHistoryStore.cmetadata,
            ChatHistoryStore.created,
            CollectionStore.name.label("collection"),
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
    return query


def history_evaluation(
    history_id: str,
    user_evaluation: bool,
    user_feedback: str | None = None,
    metadata: dict | None = None,
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
        if metadata:
            if chat_history.cmetadata is None:
                chat_history.cmetadata = {}
            chat_history.cmetadata.update(metadata)

        session.add(chat_history)
        session.commit()

    return True
