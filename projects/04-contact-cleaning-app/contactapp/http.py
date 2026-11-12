"""Tiny request/response types and a multipart reader, so the API can be tested without sockets."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: object):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


@dataclass(frozen=True)
class Request:
    method: str
    path: str
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

    def files(self) -> dict[str, bytes]:
        """Parse a multipart/form-data upload into {field name: file bytes}."""
        ctype = self.headers.get("content-type", "")
        if not ctype.startswith("multipart/form-data"):
            raise ApiError(400, "Send the files as multipart/form-data")
        msg = BytesParser(policy=policy.default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + self.body)
        out: dict[str, bytes] = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            payload = part.get_payload(decode=True)
            if name and payload:
                out[str(name)] = payload
        return out


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()


def ok(data: object, status: int = 200) -> Response:
    return Response(status, json.dumps(data).encode("utf-8"))
