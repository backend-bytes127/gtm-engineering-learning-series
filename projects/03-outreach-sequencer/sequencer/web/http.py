"""Tiny request/response types so the API can be tested without sockets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: object):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict:
        try:
            data = json.loads(self.body or b"{}")
        except json.JSONDecodeError as exc:
            raise ApiError(400, "The request body is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ApiError(400, "The request body must be a JSON object")
        return data


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()


def ok(data: object, status: int = 200) -> Response:
    return Response(status, json.dumps(data).encode("utf-8"))
