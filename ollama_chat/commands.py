"""Pure command parsing helpers for slash commands and attachment directives."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

_IMAGE_PREFIX_RE = re.compile(r"(?:^|\s)/image\s+(\S+)")
_FILE_PREFIX_RE = re.compile(r"(?:^|\s)/file\s+(\S+)")


@dataclass(frozen=True)
class ParsedDirectives:
    """Result of parsing inline /image and /file directives."""

    cleaned_text: str
    image_paths: list[str]
    file_paths: list[str]


def parse_inline_directives(text: str, *, vision_enabled: bool) -> ParsedDirectives:
    """Parse inline attachment directives from user input.

    Returns cleaned text plus any image/file paths.
    """

    raw = text

    image_paths: list[str] = []
    if vision_enabled:
        matches = _IMAGE_PREFIX_RE.findall(raw)
        for path in matches:
            image_paths.append(os.path.expanduser(path))
        raw = _IMAGE_PREFIX_RE.sub("", raw)

    file_paths: list[str] = []
    matches = _FILE_PREFIX_RE.findall(raw)
    for path in matches:
        file_paths.append(os.path.expanduser(path))
    raw = _FILE_PREFIX_RE.sub("", raw)

    return ParsedDirectives(
        cleaned_text=raw.strip(),
        image_paths=image_paths,
        file_paths=file_paths,
    )
