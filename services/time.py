from datetime import datetime, UTC


def current_date() -> str:
    return datetime.now(UTC).date().isoformat()


def current_year() -> int:
    return datetime.now(UTC).year
