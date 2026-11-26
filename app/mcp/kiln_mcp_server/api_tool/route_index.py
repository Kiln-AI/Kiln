"""An index of the REST API's routes, read from the app's route objects, that
says which route the server will run for a method and path."""

import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from fastapi import FastAPI
from fastapi.routing import APIRoute
from kiln_ai.tools.built_in_tools.kiln_api_call_tool import (
    ALLOWED_EXACT_PATHS,
    API_PATH_PREFIX,
)
from kiln_server.utils.agent_checks import is_mcp_denied


@dataclass(frozen=True)
class RouteEntry:
    path: str
    methods: frozenset[str]
    regex: re.Pattern[str]
    mcp_blocked: bool


@dataclass(frozen=True)
class RouteMatch:
    kind: Literal["found", "wrong_method", "unknown"]
    entry: RouteEntry | None = None
    path_params: Mapping[str, str] = field(default_factory=dict)
    path_methods: tuple[str, ...] = ()


class RouteIndex:
    def __init__(self, entries: tuple[RouteEntry, ...]) -> None:
        self._entries = entries

    @classmethod
    def from_app(cls, app: FastAPI) -> "RouteIndex":
        """Index the API routes of `app` (`/ping` and `/api/...`), in route
        order. Reads the route objects, not the OpenAPI document, which is slow
        to build."""
        return cls(
            tuple(
                RouteEntry(
                    path=route.path,
                    methods=frozenset(route.methods or ()),
                    regex=route.path_regex,
                    mcp_blocked=is_mcp_denied(route.openapi_extra),
                )
                for route in app.routes
                if isinstance(route, APIRoute)
                and (
                    route.path in ALLOWED_EXACT_PATHS
                    or route.path.startswith(API_PATH_PREFIX)
                )
            )
        )

    @property
    def entries(self) -> tuple[RouteEntry, ...]:
        return self._entries

    def match(self, method: str, url_path: str) -> RouteMatch:
        """The route the server runs for `method` and `url_path`: the first
        that matches both, as in the Starlette router."""
        # The server decodes the path once before routing, and the client sends
        # escapes as written, so `/api/jobs/event%73` reaches `/api/jobs/events`.
        decoded = urllib.parse.unquote(url_path)
        path_methods: set[str] = set()
        for entry in self._entries:
            found = entry.regex.match(decoded)
            if found is None:
                continue
            if method in entry.methods:
                return RouteMatch(
                    kind="found", entry=entry, path_params=found.groupdict()
                )
            path_methods |= entry.methods
        if path_methods:
            return RouteMatch(
                kind="wrong_method", path_methods=tuple(sorted(path_methods))
            )
        return RouteMatch(kind="unknown")
