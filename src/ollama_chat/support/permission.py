from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PermissionRequest:
    permission: str
    patterns: list[str]
    always: list[str]
    metadata: dict[str, Any]


def evaluate(_req: PermissionRequest) -> bool:  # pragma: no cover - stub
    """Placeholder permission evaluation.

    A real implementation would consult a ruleset. Here we always return True
    and rely on the caller to use ctx.ask() to request interactive approval.
    """
    return True
