from typing import NoReturn

from fastapi import HTTPException, status


def raise_conversation_not_found() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "CONVERSATION_NOT_FOUND",
            "message": "The requested conversation was not found.",
        },
    )
