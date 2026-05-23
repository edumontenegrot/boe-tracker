"""BOIB — Butlletí Oficial de les Illes Balears.

Los boletines usan IDs secuenciales, no fechas en la URL.
Se resuelve la fecha consultando el índice anual:
  https://www.caib.es/eboibfront/ca/{YYYY}/
que muestra un calendario con enlaces a cada número.
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.caib.es"
YEAR_INDEX_URL = "https://www.caib.es/eboibfront/ca/{year}/"

SECTION_MAP = {
    "DISPOSICIONS GENERALS": "I",
    "DISPOSICIONES GENERALES": "I",
    "ALTRES DISPOSICIONS": "III",
    "OTRAS DISPOSICIONES": "III",
}


class BOIBScraper(BaseScraper):
    bulletin_id = "BOIB"
    bulletin_name = "Butlletí Oficial de les Illes Balears"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOIB] Fetching sumario for %s", target_date.isoformat())

        index_url = YEAR_INDEX_URL.format(year=target_date.strftime("%Y"))
        resp = self._safe_get(index_url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_url = self._find_date_link(soup, target_date)
        if not boletin_url:
            logger.warning("[BOIB] No boletín found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_url, target_date.isoformat())

    def _find_date_link(self, soup: BeautifulSoup, target_date: date) -> Optional[str]:
        """Find the bulletin detail URL for the given date from the year index."""
        # The calendar shows dates; links look like /eboibfront/ca/2026/12345/
        patterns = [
            target_date.strftime("%d/%m/%Y"),
            target_date.strftime("%Y-%m-%d"),
            target_date.strftime("%d-%m-%Y"),
        ]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not re.search(r"/eboibfront/\w+/\d{4}/\d+", href):
                continue
            cell_text = ""
            # Check anchor text and surrounding td/li
            if a.parent:
                cell_text = a.parent.get_text(" ", strip=True)
            full_text = a.get_text(strip=True) + " " + cell_text
            for p in patterns:
                if p in full_text or p in href:
                    return href if href.startswith("http") else BASE_URL + href
        return None

    def _parse_boletin(self, url: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        resp = self._safe_get(url)
        if resp is None:
            return acts

        soup = BeautifulSoup(resp.text, "lxml")
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "td"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            for key, roman in SECTION_MAP.items():
                if key in upper and len(upper) < 80:
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()
                    break
            else:
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV)\b", upper)
                if sec_match:
                    roman = sec_match.group(1)
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()

            if current_section is None:
                continue

            if tag.name in ("h3", "h4") and not tag.find("a"):
                current_organism = text
                continue

            link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            if not link:
                continue

            href = link["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True) or text
            act_id = "BOIB-" + pdf_url.split("/")[-1].replace(".pdf", "")

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id=act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[BOIB] Found %d acts in sections I/III", len(acts))
        return acts
