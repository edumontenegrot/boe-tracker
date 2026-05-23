"""PDF text extractor — wraps pdfplumber for pipeline use.

Returns a plain dict so the caller never has to handle exceptions.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_pdf(path: Path) -> dict:
    """Extract text from a PDF file.

    Returns:
        {"text": str, "pages": int}
        On any failure returns {"text": "", "pages": 0} and logs a warning.
    """
    try:
        import pdfplumber  # deferred import — not needed by scrapers
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
            text = "\n\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).strip()
        return {"text": text, "pages": pages}
    except Exception as exc:
        logger.warning("PDF extraction failed for %s: %s", path, exc)
        return {"text": "", "pages": 0}
