"""BOCM — Boletín Oficial de la Comunidad de Madrid.

Endpoint XML: https://www.bocm.es/boletin/bocm-{YYYYMMDD}-{N}.xml
Sumario HTML: https://www.bocm.es/boletin-bocm-{YYYYMMDD}-{N}
API search: https://www.bocm.es/boletin/buscador?fecha={DD/MM/YYYY}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

SUMARIO_URL = "https://www.bocm.es/boletin/buscador"
PDF_BASE = "https://www.bocm.es"

# BOCM section identifiers in HTML
SECTION_MAP = {
    "I": "I",
    "III": "III",
    "DISPOSICIONES GENERALES": "I",
    "OTRAS DISPOSICIONES": "III",
}


class BOCMScraper(BaseScraper):
    bulletin_id = "BOCM"
    bulletin_name = "Boletín Oficial de la Comunidad de Madrid"
    base_url = "https://www.bocm.es"

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        date_str = target_date.strftime("%d/%m/%Y")

        logger.info("[BOCM] Fetching sumario for %s", target_date.isoformat())
        resp = self._safe_get(SUMARIO_URL, params={"fecha": date_str})
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_link = self._find_boletin_link(soup, target_date)
        if not boletin_link:
            logger.warning("[BOCM] No boletín found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_link, target_date.isoformat())

    def _find_boletin_link(self, soup: BeautifulSoup, target_date: date) -> Optional[str]:
        # Look for the day's bulletin link in search results
        date_pattern = target_date.strftime("%Y%m%d")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if date_pattern in href and "boletin" in href.lower():
                return href if href.startswith("http") else self.base_url + href
        return None

    def _parse_boletin(self, url: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        resp = self._safe_get(url)
        if resp is None:
            return acts

        soup = BeautifulSoup(resp.text, "lxml")
        current_section = None
        current_section_name = ""

        for element in soup.find_all(["h2", "h3", "h4", "div", "li"]):
            text = element.get_text(strip=True).upper()

            # Detect section headers
            section_match = re.match(r"^SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3}|IX|XI{0,3})", text)
            if section_match or text in SECTION_MAP:
                roman = SECTION_MAP.get(text, "")
                if not roman and section_match:
                    roman = section_match.group(1)
                if roman in INCLUDED_SECTIONS:
                    current_section = roman
                    current_section_name = text.title()
                else:
                    current_section = None
                continue

            if current_section is None:
                continue

            # Extract act entries
            link = element.find("a", href=True)
            if link and (".pdf" in link["href"].lower() or "/bocm-" in link["href"].lower()):
                title = link.get_text(strip=True)
                pdf_url = link["href"]
                if not pdf_url.startswith("http"):
                    pdf_url = self.base_url + pdf_url

                # Try to find a PDF link specifically
                pdf_link = element.find("a", href=re.compile(r"\.pdf$", re.I))
                if pdf_link:
                    pdf_href = pdf_link["href"]
                    pdf_url = pdf_href if pdf_href.startswith("http") else self.base_url + pdf_href

                act_id = re.search(r"BOCM-\d{8}-\d+", pdf_url, re.I)
                act_id = act_id.group(0).upper() if act_id else pdf_url.split("/")[-1]

                acts.append(Act(
                    bulletin_id=self.bulletin_id,
                    act_id=act_id,
                    title=title,
                    section=current_section,
                    section_name=current_section_name,
                    rank="",
                    organism="",
                    pdf_url=pdf_url,
                    summary="",
                    pub_date=pub_date,
                ))

        logger.info("[BOCM] Found %d acts in sections I/III", len(acts))
        return acts
