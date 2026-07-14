"""
Text normalization for extracted document content.

Normalization is deterministic: the same input always produces the same output.

Steps:
  1. Unicode normalization (NFC)
  2. Line ending normalization (CRLF → LF)
  3. Whitespace normalization (tabs → spaces, collapse multiple spaces)
  4. Remove repeated blank lines (max one blank line between paragraphs)
  5. Trim leading/trailing whitespace
  6. Preserve paragraph/slide/page boundaries where possible
"""

import re
import unicodedata


def normalize_text(text: str, preserve_boundaries: bool = True) -> str:
    """Normalize extracted text deterministically.

    Args:
        text: Raw extracted text.
        preserve_boundaries: If True, preserve paragraph boundaries
            (blank lines). Default True.

    Returns:
        Normalized text.
    """
    if not text:
        return ""

    # 1. Unicode normalization (NFC) — canonical composed form
    text = unicodedata.normalize("NFC", text)

    # 2. Line ending normalization
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Replace tabs with single space
    text = text.replace("\t", " ")

    # 4. Collapse multiple horizontal spaces (but keep newlines)
    text = re.sub(r"[ \t]+", " ", text)

    # 5. Remove blank lines at start and end
    text = text.strip("\n")

    if preserve_boundaries:
        # 6. Ensure at most one blank line between paragraphs
        #    (multiple newlines → exactly two newlines)
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        # Collapse all newlines to spaces
        text = re.sub(r"\n+", " ", text)

    # 7. Trim leading/trailing whitespace
    text = text.strip()

    return text
