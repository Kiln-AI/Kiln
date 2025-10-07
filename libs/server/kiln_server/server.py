import argparse
from typing import Sequence

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .custom_errors import connect_custom_errors
from .document_api import connect_document_api
from .project_api import connect_project_api
from .prompt_api import connect_prompt_api
from .run_api import connect_run_api
from .task_api import connect_task_api


def make_app(lifespan=None):
    app = FastAPI(
        title="Kiln AI Server",
        summary="A REST API for the Kiln AI datamodel.",
        description="Learn more about Kiln AI at https://github.com/kiln-ai/kiln",
        lifespan=lifespan,
    )

    @app.get("/ping")
    def ping():
        return "pong"

    connect_project_api(app)
    connect_task_api(app)
    connect_prompt_api(app)
    connect_run_api(app)
    connect_document_api(app)
    connect_custom_errors(app)

    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://localhost:5173",
        "https://127.0.0.1:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Kiln AI  REST Server.")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host for network transports."
    )
    parser.add_argument(
        "--port", type=int, default=8757, help="Port for network transports."
    )
    parser.add_argument(
        "--log-level",
        default="info",
        help="Log level for the server when using network transports.",
    )
    parser.add_argument(
        "--auto-reload",
        action="store_true",
        help="Enable auto-reload for the server.",
    )
    return parser


app = make_app()


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    uvicorn.run(
        "kiln_server.server:app",
        host=args.host,
        port=args.port,
        reload=args.auto_reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
