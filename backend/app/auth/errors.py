from typing import NoReturn

from fastapi import HTTPException, status


def raise_invalid_credentials() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_CREDENTIALS",
            "message": "The email or password is incorrect.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_unauthorized() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "UNAUTHORIZED",
            "message": "Valid authentication is required.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )
