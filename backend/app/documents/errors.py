from typing import NoReturn

from fastapi import HTTPException, status


def raise_document_error(status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def raise_document_not_found() -> NoReturn:
    raise_document_error(
        status.HTTP_404_NOT_FOUND,
        "DOCUMENT_NOT_FOUND",
        "The requested document was not found.",
    )


def raise_delete_forbidden() -> NoReturn:
    raise_document_error(
        status.HTTP_403_FORBIDDEN,
        "DOCUMENT_DELETE_FORBIDDEN",
        "Only the uploader can delete this document.",
    )
