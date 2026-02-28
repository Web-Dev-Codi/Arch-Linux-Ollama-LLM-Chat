"""Event-driven architecture components.

Phase 4.1: Event bus system for decoupled component communication.
"""

from .bus import Event, EventBus

__all__ = ["EventBus", "Event"]
