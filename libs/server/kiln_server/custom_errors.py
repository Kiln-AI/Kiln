from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def format_error_loc(loc: tuple):
    if not loc:
        return ""
    formatted = []
    # Skip the first item if it's "body" (case-insensitive)
    start_index = 1 if loc and loc[0].lower() == "body" else 0
    for i, item in enumerate(loc[start_index:]):
        if item is not None and item != "":
            if isinstance(item, str):
                formatted.append(
                    item.capitalize() if i == 0 else "." + item.capitalize()
                )
            elif isinstance(item, int):
                formatted.append(f"[{item}]")
            else:
                formatted.append(str(item))
    return "".join(formatted)


def connect_custom_errors(app: FastAPI):
    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError | ValidationError
    ):
        # Write user friendly error messages
        error_messages = []
        for error in exc.errors():
            message = error.get("msg", "Unknown error")
            loc = error.get("loc")

            # Custom helpers for common errors
            if "String should match pattern '^[A-Za-z0-9 _-]+$'" == message:
                message = "must consist of only letters, numbers, spaces, hyphens, and underscores"

            error_messages.append(f"{format_error_loc(loc)}: {message}")

        def serialize_error(error):
            return {
                "type": error.get("type"),
                "loc": [str(loc) for loc in error.get("loc", [])],
                "msg": error.get("msg"),
                "input": str(error.get("input")),
                "ctx": {str(k): str(v) for k, v in error.get("ctx", {}).items()},
            }

        serialized_errors = [serialize_error(error) for error in exc.errors()]

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_messages": error_messages,
                "message": ".\n".join(error_messages),
                "source_errors": serialized_errors,
            },
        )

    # Wrap in a format that the client can understand (message, and error_messages)
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
        )
