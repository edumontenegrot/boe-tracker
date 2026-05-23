"""DOGA — Diario Oficial de Galicia.

Sumario: https://www.xunta.gal/diario-oficial-galicia/contido?data={DD-MM-YYYY}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.xunta.gal"
SUMARIO_URL = "https://www.xunta.gal/diario-oficial-galicia/contido"

SECTION_KEYWORDS = {
    "DISPOSICIÓNS XERAIS": "I",
    "DISPOSICIONES GENERALES": "I",
    "OUTRAS DISPOSICIÓNS": "III",
    "OTRAS DISPOSICIONES": "III",
    "I. DISPOSICIÓNS": "I",
    "III. OUTRAS": "III",
}


class DOGAScraper(BaseScraper):
    bulletin_id = "DOGA"
    bulletin_name = "Diario Oficial de Galicia"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        date_str = target_date.strftime("%d-%m-%Y")
        logger.info("[DOGA] Fetching sumario for %s", target_date.isoformat())

        resp = self._safe_get(SUMARIO_URL, params={"data": date_str})
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse(soup, target_date.isoformat())

    def _parse(self, soup: BeautifulSoup, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div", "span"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            # Section detection
            for key, roman in SECTION_KEYWORDS.items():
                if key in upper and len(upper) < 80:
                    if roman in INCLUDED_SECTIONS:
                        current_section = roman
                        current_section_name = text.strip()
                    else:
                        current_section = None
                    break
            else:
                sec_match = re.search(r"\b(I{1,3}V?|IV)\.\s+", upper)
                if sec_match and len(upper) < 80:
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
                act_id="DOGA-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[DOGA] Found %d acts in sections I/III", len(acts))
        return acts
