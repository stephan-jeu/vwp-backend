from __future__ import annotations

"""Application-wide logging utilities.

This module exposes a shared `logger` instance configured to use the
`uvicorn.error` logger so log messages consistently appear in the
server output.
"""

import logging

logger = logging.getLogger("uvicorn.error")
