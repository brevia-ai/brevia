"""Dates utilities"""
from datetime import datetime, time


def date_filter(date_str: str | None, type_str: str = 'min'):
    """
    Parses a date string into a datetime object with combined time information.

    Args:
        date_str (str): A string representing a date in the format 'YYYY-MM-DD'.
            None if no specific date is provided.

        type_str (str): Indicates whether to create a maximum or minimum date filter.
            Valid values are 'max' or 'min'. If None 'min' is i
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
