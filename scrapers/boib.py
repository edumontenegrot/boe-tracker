"""BOIB — Butlletí Oficial de les Illes Balears.

Sumario: https://www.caib.es/eboib/detail?id={ID}&lang=ca
Buscador: https://www.caib.es/eboib/buscador?data={DD/MM/YYYY}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.caib.es"
SEARCH_URL = "https://www.caib.es/eboib/buscador"

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

        resp = self._safe_get(
            SEARCH_URL,
            params={"data": target_date.strftime("%d/%m/%Y")},
        )
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_link = self._find_boletin_link(soup)
        if not boletin_link:
            logger.warning("[BOIB] No boletín found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_link, target_date.isoformat())

    def _find_boletin_link(self, soup: BeautifulSoup) -> Optional[str]:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/eboib/detail" in href or "sumari" in href.lower():
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

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            for key, roman in SECTION_MAP.items():
                if key in upper and len(upper) < 80:
                    if roman in INCLUDED_SECTIONS:
                        current_section = roman
                        current_section_name = text.strip()
                    else:
                        current_section = None
                    break
            else:
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV)\b", upper)
                if sec_match:
                    roman = sec_match.group(1)
                    if roman in INCLUDED_SECTIONS:
                        current_section = roman
                        current_section_name = text.strip()
                    else:
                        current_section = None

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
                act_id="BOIB-" + act_id,
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
