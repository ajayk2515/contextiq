from typing import NoReturn

from fastapi import HTTPException, status


def raise_chat_unavailable(code: str, message: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message},
    )
