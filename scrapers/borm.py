"""BORM — Boletín Oficial de la Región de Murcia.

Sumario: https://www.borm.es/borm/vista/boletin/index.jsf  (búsqueda por fecha)
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.borm.es"
SEARCH_URL = "https://www.borm.es/borm/vista/boletin/index.jsf"


class BORMScraper(BaseScraper):
    bulletin_id = "BORM"
    bulletin_name = "Boletín Oficial de la Región de Murcia"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BORM] Fetching sumario for %s", target_date.isoformat())

        # BORM uses a direct URL pattern for each day
        date_str = target_date.strftime("%Y%m%d")
        url = f"{BASE_URL}/borm/vista/boletin/leerBoletin.jsf?fecha={date_str}"
        resp = self._safe_get(url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse(soup, target_date.isoformat())

    def _parse(self, soup: BeautifulSoup, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "span"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
            if sec_match:
                roman = sec_match.group(1)
                if roman in INCLUDED_SECTIONS:
                    current_section = roman
                    current_section_name = text.strip()
                else:
                    current_section = None
                current_organism = ""
                continue

            if current_section is None:
                continue

            if tag.name in ("h3", "h4") and not tag.find("a"):
                current_organism = text
                continue

            link = tag.find("a", href=True)
            if not link:
                continue

            href = link["href"]
            if ".pdf" not in href.lower():
                continue

            title = link.get_text(strip=True) or text
            pdf_url = href if href.startswith("http") else BASE_URL + href
            act_id = pdf_url.split("/")[-1].replace(".pdf", "")

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id="BORM-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[BORM] Found %d acts in sections I/III", len(acts))
        return acts
