from fastapi import FastAPI

# Scalar is only available in dev dependencies group
try:
    from scalar_fastapi import get_scalar_api_reference

    SCALAR_AVAILABLE = True
except ImportError:
    SCALAR_AVAILABLE = False


def connect_dev_tools(app: FastAPI):
    if SCALAR_AVAILABLE:

        @app.get("/scalar", include_in_schema=False)
        async def scalar_html():
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
            )
