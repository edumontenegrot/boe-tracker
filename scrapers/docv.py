"""DOCV — Diari Oficial de la Comunitat Valenciana.

API/Sumario: https://dogv.gva.es/datos/2026/05/23/xml/0090-2026.xml  (formato YYYY/MM/DD)
Buscador: https://dogv.gva.es/portal/ficha_disposicion_pc.jsp?sig={id}&L=1
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://dogv.gva.es"
# Direct XML index per date
XML_URL = "https://dogv.gva.es/datos/{year}/{month}/{day}/xml/"
SEARCH_URL = "https://dogv.gva.es/portal/buscador/api/search"

SECTION_MAP = {
    "DISPOSICIONS GENERALS": "I",
    "DISPOSICIONES GENERALES": "I",
    "ALTRES DISPOSICIONS": "III",
    "OTRAS DISPOSICIONES": "III",
}


class DOCVScraper(BaseScraper):
    bulletin_id = "DOCV"
    bulletin_name = "Diari Oficial de la Comunitat Valenciana"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[DOCV] Fetching sumario for %s", target_date.isoformat())

        # Try the HTML sumario search first
        search_url = (
            f"{BASE_URL}/portal/buscador/sumario.jsp"
            f"?fechaIni={target_date.strftime('%d/%m/%Y')}"
            f"&fechaFin={target_date.strftime('%d/%m/%Y')}"
        )
        resp = self._safe_get(search_url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_link = self._find_boletin_link(soup)
        if not boletin_link:
            logger.warning("[DOCV] No boletín found for %s", target_date.isoformat())
            return []

        resp2 = self._safe_get(boletin_link)
        if resp2 is None:
            return []

        soup2 = BeautifulSoup(resp2.text, "lxml")
        return self._parse(soup2, target_date.isoformat())

    def _find_boletin_link(self, soup: BeautifulSoup) -> Optional[str]:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "sumari" in href.lower() or "sumario" in href.lower():
                return href if href.startswith("http") else BASE_URL + href
        return None

    def _parse(self, soup: BeautifulSoup, pub_date: str) -> list[Act]:
        acts: list[Act] = []
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
                act_id="DOCV-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[DOCV] Found %d acts in sections I/III", len(acts))
        return acts
