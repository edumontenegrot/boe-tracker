"""BOA — Boletín Oficial de Aragón.

Sumario: https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BOLE&DOCR=1&SEC=FIRMA&SORT=-NBOL&SEPARADOR=&&NBOL-C=%3D{NUM}
Buscador por fecha: https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BOLE&DOCR=1&SORT=-NBOL&SEC=FIRMA&SEPARADOR=&&FECH-C=%3D{YYYYMMDD}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boa.aragon.es"
SEARCH_URL = "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI"


class BOAScraper(BaseScraper):
    bulletin_id = "BOA"
    bulletin_name = "Boletín Oficial de Aragón"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOA] Fetching sumario for %s", target_date.isoformat())

        date_str = target_date.strftime("%Y%m%d")
        params = {
            "CMD": "VERDOC",
            "BASE": "BOLE",
            "DOCR": "1",
            "SORT": "-NBOL",
            "SEC": "FIRMA",
            "SEPARADOR": "",
            "FECH-C": f"={date_str}",
        }
        resp = self._safe_get(SEARCH_URL, params=params)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_link = self._find_boletin_link(soup)
        if not boletin_link:
            logger.warning("[BOA] No boletín found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_link, target_date.isoformat())

    def _find_boletin_link(self, soup: BeautifulSoup) -> Optional[str]:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "sumario" in href.lower() or "EBOA" in href:
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

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "td"]):
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
                continue

            if current_section is None:
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
                act_id="BOA-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism="",
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[BOA] Found %d acts in sections I/III", len(acts))
        return acts
