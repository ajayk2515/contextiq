import pytest
from pydantic import ValidationError

from app.config import Settings


def test_cors_origins_are_parsed_from_comma_separated_value() -> None:
    settings = Settings(
        cors_origins="https://app.example.com, https://admin.example.com",  # type: ignore[arg-type]
    )

    assert settings.cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_database_url_requires_async_postgresql() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///local.db")


def test_document_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError):
        Settings(chunk_size=500, chunk_overlap=500)
