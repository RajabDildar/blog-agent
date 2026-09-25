"""DeclarativeBase for SQLAlchemy application models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all application ORM models."""
    pass
