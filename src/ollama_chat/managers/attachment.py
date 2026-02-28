"""Attachment handling for images and files.

Extracted from app.py during Phase 2B refactoring.
Manages file/image attachment dialogs, validation, and state management.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ollama_chat.capabilities import AttachmentState

LOGGER = logging.getLogger(__name__)

# Image file extensions accepted for vision attachments
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
)


class AttachmentManager:
    """Manages file and image attachments.

    Responsibilities:
    - Opening native file dialogs
    - Validating attachments (size, type, existence)
    - Managing attachment state
    - Image/file path validation

    Extracted from OllamaChatApp to separate attachment concerns.
    """

    def __init__(
        self,
        attachment_state: AttachmentState,
        *,
        max_image_bytes: int = 10 * 1024 * 1024,  # 10 MB
        max_file_bytes: int = 2 * 1024 * 1024,  # 2 MB
    ) -> None:
        """Initialize attachment manager.

        Args:
            attachment_state: AttachmentState instance for tracking attachments
            max_image_bytes: Maximum size for image attachments
            max_file_bytes: Maximum size for file attachments
        """
        self.attachments = attachment_state
        self.max_image_bytes = max_image_bytes
        self.max_file_bytes = max_file_bytes
        self._image_dialog_active = False
        self._on_status_update: Callable[[str], None] | None = None

    def on_status_update(self, callback: Callable[[str], None]) -> None:
        """Register callback for status/subtitle updates.

        Args:
            callback: Function to call with status messages
        """
        self._on_status_update = callback

    @staticmethod
    def is_image_path(path: str) -> bool:
        """Check if path has an image file extension.

        Args:
            path: File path to check

        Returns:
            True if path ends with image extension
        """
        return Path(path).suffix.lower() in IMAGE_EXTENSIONS

    async def open_dialog(
        self,
        mode: str,  # "image" or "file"
        open_native_dialog: Callable,  # Async function to open native dialog
        open_modal_dialog: Callable,  # Function to open modal dialog screen
    ) -> None:
        """Open attachment dialog (native file picker or modal fallback).

        Args:
            mode: "image" or "file"
            open_native_dialog: Async function that opens native file picker
            open_modal_dialog: Function that opens modal dialog as fallback
        """
        # Prevent double-launch of image dialog
        if mode == "image" and self._image_dialog_active:
            return

        if mode == "image":
            self._image_dialog_active = True
            file_filter = [("Images", [f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS)])]
            title = "Attach image"
            callback = self.on_image_dismissed
        else:
            file_filter = None
            title = "Attach file"
            callback = self.on_file_dismissed

        try:
            path = await open_native_dialog(title=title, file_filter=file_filter)
            if path is None:
                # Native dialog not available - use modal fallback
                open_modal_dialog(callback=callback)
                return
            callback(path)
        finally:
            if mode == "image":
                self._image_dialog_active = False

    def on_image_dismissed(self, path: str | None) -> None:
        """Handle image attachment dialog dismissal.

        Args:
            path: Selected image path, or None if cancelled
        """
        self._image_dialog_active = False

        if not path:
            return

        ok, message, resolved = self.validate_attachment(
            path,
            kind="image",
            max_bytes=self.max_image_bytes,
            allowed_extensions=IMAGE_EXTENSIONS,
        )

        if not ok or resolved is None:
            if self._on_status_update:
                self._on_status_update(message)
            LOGGER.warning(f"Image validation failed: {message}")
            return

        self.attachments.add_image(str(resolved))
        if self._on_status_update:
            count = len(self.attachments.images)
            self._on_status_update(f"Image attached: {resolved.name} ({count} total)")

    def on_file_dismissed(self, path: str | None) -> None:
        """Handle file attachment dialog dismissal.

        Args:
            path: Selected file path, or None if cancelled
        """
        if not path:
            return

        ok, message, resolved = self.validate_attachment(
            path,
            kind="file",
            max_bytes=self.max_file_bytes,
            allowed_extensions=None,  # Allow all file types
        )

        if not ok or resolved is None:
            if self._on_status_update:
                self._on_status_update(message)
            LOGGER.warning(f"File validation failed: {message}")
            return

        self.attachments.add_file(str(resolved))
        if self._on_status_update:
            self._on_status_update(f"File attached: {resolved.name}")

    @staticmethod
    def validate_attachment(
        path: str,
        *,
        kind: str,  # "image" or "file"
        max_bytes: int,
        allowed_extensions: frozenset[str] | None,
    ) -> tuple[bool, str, Path | None]:
        """Validate attachment path, size, and type.

        Args:
            path: Path to attachment file
            kind: Type of attachment ("image" or "file")
            max_bytes: Maximum file size in bytes
            allowed_extensions: Set of allowed extensions, or None for any

        Returns:
            Tuple of (success, error_message, resolved_path)
        """
        try:
            resolved = Path(path).expanduser().resolve()

            if not resolved.exists():
                return False, f"{kind.capitalize()} not found: {path}", None

            if not resolved.is_file():
                return False, f"Not a file: {path}", None

            # Check extension if restrictions specified
            if allowed_extensions:
                if resolved.suffix.lower() not in allowed_extensions:
                    exts = ", ".join(sorted(allowed_extensions))
                    return False, f"Invalid {kind} type. Allowed: {exts}", None

            # Check file size
            size = resolved.stat().st_size
            if size > max_bytes:
                max_mb = max_bytes / (1024 * 1024)
                return (
                    False,
                    f"{kind.capitalize()} too large (max {max_mb:.1f}MB)",
                    None,
                )

            return True, "", resolved

        except Exception as exc:
            return False, f"Error validating {kind}: {exc}", None

    def validate_attachments_batch(
        self,
        image_paths: list[str],
        file_paths: list[str],
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate multiple attachments at once.

        Useful for batch validation in send_user_message.

        Args:
            image_paths: List of image paths to validate
            file_paths: List of file paths to validate

        Returns:
            Tuple of (valid_images, valid_files, error_messages)
        """
        valid_images = []
        valid_files = []
        errors = []

        for img_path in image_paths:
            ok, message, resolved = self.validate_attachment(
                img_path,
                kind="image",
                max_bytes=self.max_image_bytes,
                allowed_extensions=IMAGE_EXTENSIONS,
            )
            if ok and resolved:
                valid_images.append(str(resolved))
            else:
                errors.append(message)
                LOGGER.warning(f"Image validation failed: {message}")

        for file_path in file_paths:
            ok, message, resolved = self.validate_attachment(
                file_path,
                kind="file",
                max_bytes=self.max_file_bytes,
                allowed_extensions=None,
            )
            if ok and resolved:
                valid_files.append(str(resolved))
            else:
                errors.append(message)
                LOGGER.warning(f"File validation failed: {message}")

        return valid_images, valid_files, errors
