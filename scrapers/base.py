"""Base scraper class with common functionality."""

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

INCLUDED_SECTIONS = {"I", "III"}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BOETracker/1.0; "
        "+https://github.com/your-org/boe-tracker)"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


def build_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class Act:
    """A single legislative act extracted from a bulletin."""

    __slots__ = (
        "bulletin_id", "act_id", "title", "section", "section_name",
        "rank", "organism", "pdf_url", "summary", "date",
    )

    def __init__(
        self,
        bulletin_id: str,
        act_id: str,
        title: str,
        section: str,
        section_name: str,
        rank: str,
        organism: str,
        pdf_url: str,
        summary: str,
        pub_date: str,
    ):
        self.bulletin_id = bulletin_id
        self.act_id = act_id
        self.title = title
        self.section = section
        self.section_name = section_name
        self.rank = rank
        self.organism = organism
        self.pdf_url = pdf_url
        self.summary = summary
        self.date = pub_date

    def to_dict(self) -> dict:
        return {
            "id": self.act_id,
            "title": self.title,
            "section": self.section,
            "section_name": self.section_name,
            "rank": self.rank,
            "organism": self.organism,
            "pdf_url": self.pdf_url,
            "summary": self.summary,
            "date": self.date,
        }


class BaseScraper(ABC):
    """Abstract base class for all bulletin scrapers."""

    bulletin_id: str = ""
    bulletin_name: str = ""
    base_url: str = ""

    def __init__(self):
        self.session = build_session()

    @abstractmethod
    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        """Fetch and return filtered acts for the given date."""

    def _is_included_section(self, section_num: str) -> bool:
        return section_num.strip().upper() in INCLUDED_SECTIONS

    def _safe_get(self, url: str, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, timeout=(10, 30), **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning("[%s] GET %s failed: %s", self.bulletin_id, url, exc)
            return None
