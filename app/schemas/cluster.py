from __future__ import annotations

from pydantic import BaseModel


class ClusterBase(BaseModel):
    """Shared Cluster fields used for create and read operations."""

    project_id: int
    address: str


class ClusterCreate(ClusterBase):
    """Payload for creating a Cluster."""


class ClusterRead(ClusterBase):
    """Read model for Cluster."""

    id: int

    model_config = {"from_attributes": True}
