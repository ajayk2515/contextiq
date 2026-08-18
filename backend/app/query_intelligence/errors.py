from typing import NoReturn

from fastapi import HTTPException, status


def raise_query_not_found() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "QUERY_NOT_FOUND",
            "message": "The requested query was not found.",
        },
    )
