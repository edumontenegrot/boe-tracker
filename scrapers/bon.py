"""BON — Boletín Oficial de Navarra.

Sumario: https://bon.navarra.es/es/boletin/-/sumario/{YYYYMMDD}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://bon.navarra.es"
SUMARIO_URL = "https://bon.navarra.es/es/boletin/-/sumario/{datestr}"

SECTION_MAP = {
    "DISPOSICIONES GENERALES": "I",
    "XEDAPEN OROKORRAK": "I",
    "OTRAS DISPOSICIONES": "III",
    "BESTE XEDAPEN BATZUK": "III",
}


class BONScraper(BaseScraper):
    bulletin_id = "BON"
    bulletin_name = "Boletín Oficial de Navarra"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        url = SUMARIO_URL.format(datestr=target_date.strftime("%Y%m%d"))
        logger.info("[BON] Fetching sumario for %s", target_date.isoformat())

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
                act_id="BON-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[BON] Found %d acts in sections I/III", len(acts))
        return acts
