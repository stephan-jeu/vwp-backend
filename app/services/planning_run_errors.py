from __future__ import annotations


class PlanningRunError(RuntimeError):
    """Raised when a planning run did not produce an acceptable result.

    This is used to distinguish expected planning failures (e.g., solver returns no
    acceptable solution) from generic programming errors.

    Args:
        message: High-level human-readable message for logs.
        technical_detail: Optional technical detail (status, gap, traceback, etc.).
    """

    def __init__(self, message: str, *, technical_detail: str | None = None) -> None:
        super().__init__(message)
        self.technical_detail = technical_detail
