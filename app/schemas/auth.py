from __future__ import annotations

from pydantic import BaseModel


class GoogleCallbackRequest(BaseModel):
    code: str
