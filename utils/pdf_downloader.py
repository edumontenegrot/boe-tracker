"""PDF downloader with rate-limiting, size cap, and per-file error isolation."""

import logging
import time
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB
DELAY_BETWEEN_DOWNLOADS = 1.5     # seconds


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (compatible; BOETracker/1.0; "
            "+https://github.com/your-org/boe-tracker)"
        )
    })
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class PDFDownloader:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = _build_session()
        self._last_download_time: float = 0.0

    def download(self, url: str, filename: str) -> Optional[Path]:
        """Download a PDF, respecting rate limits and size cap.

        Returns the local path on success, None on failure.
        """
        if not url:
            logger.warning("Empty URL for %s, skipping", filename)
            return None

        dest = self.output_dir / filename
        if dest.exists():
            logger.debug("Already downloaded: %s", dest)
            return dest

        self._rate_limit()

        try:
            resp = self.session.get(url, stream=True, timeout=60)
            resp.raise_for_status()

            content_length = int(resp.headers.get("Content-Length", 0))
            if content_length > MAX_PDF_BYTES:
                logger.warning(
                    "PDF %s too large (%d bytes > %d limit), skipping",
                    filename, content_length, MAX_PDF_BYTES,
                )
                return None

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
                logger.warning(
                    "URL %s does not appear to be a PDF (Content-Type: %s), skipping",
                    url, content_type,
                )
                return None

            data = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                data.extend(chunk)
                if len(data) > MAX_PDF_BYTES:
                    logger.warning(
                        "PDF %s exceeded size limit during download, skipping", filename
                    )
                    return None

            dest.write_bytes(data)
            logger.info("Downloaded %s (%d KB)", filename, len(data) // 1024)
            return dest

        except requests.RequestException as exc:
            logger.error("Failed to download %s from %s: %s", filename, url, exc)
            return None
        finally:
            self._last_download_time = time.monotonic()

    def _rate_limit(self):
        elapsed = time.monotonic() - self._last_download_time
        wait = DELAY_BETWEEN_DOWNLOADS - elapsed
        if wait > 0:
            time.sleep(wait)

    def download_batch(
        self, items: list[tuple[str, str]]
    ) -> dict[str, Optional[Path]]:
        """Download multiple (url, filename) pairs.

        Returns a dict mapping filename → local path (or None on failure).
        """
        results: dict[str, Optional[Path]] = {}
        for url, filename in items:
            results[filename] = self.download(url, filename)
        return results
