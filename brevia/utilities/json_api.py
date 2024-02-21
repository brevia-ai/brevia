"""Utility functions to format sqlalchemy query data as JSON API."""
from sqlalchemy.orm import Query


def query_data_pagination(query: Query, page: int = 1, page_size: int = 50):
    """
        Format query data with pagination
    """
    page = max(1, page)  # min page number is 1
    page_size = min(1000, page_size)  # max page size is 1000
    offset = (page - 1) * page_size

    count = query.count()
    results = [u._asdict() for u in query.offset(offset).limit(page_size).all()]
    pcount = int(count / page_size)
    pcount += 0 if (count % page_size) == 0 else 1

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
