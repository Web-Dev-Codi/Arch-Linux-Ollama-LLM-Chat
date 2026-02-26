"""Event-driven architecture components.

Phase 4.1: Event bus system for decoupled component communication.
"""

from .bus import EventBus, Event

__all__ = ["EventBus", "Event"]
