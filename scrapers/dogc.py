"""DOGC — Diari Oficial de la Generalitat de Catalunya.

API REST: https://dogc.gencat.cat/ca/inici/
Endpoint: https://dogc.gencat.cat/AppJava/action/consultaDOGCPortal.do
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://dogc.gencat.cat"
SUMARIO_URL = (
    "https://dogc.gencat.cat/AppJava/action/consultaDOGCPortal.do"
    "?action=consultaHistoric&tematica=0&dataPublicacioIni={date}&dataPublicacioFi={date}"
)
PDF_BASE = "https://portaldogc.gencat.cat"

SECTION_MAP = {
    "DISPOSICIONS GENERALS": "I",
    "DISPOSICIONES GENERALES": "I",
    "ALTRES DISPOSICIONS": "III",
    "OTRAS DISPOSICIONES": "III",
    "I": "I",
    "III": "III",
}


class DOGCScraper(BaseScraper):
    bulletin_id = "DOGC"
    bulletin_name = "Diari Oficial de la Generalitat de Catalunya"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        date_str = target_date.strftime("%d/%m/%Y")

        logger.info("[DOGC] Fetching sumario for %s", target_date.isoformat())
        url = SUMARIO_URL.format(date=date_str)
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

        for row in soup.find_all(["tr", "div", "li"]):
            text = row.get_text(strip=True)
            upper = text.upper()

            # Detect section headings
            for key, roman in SECTION_MAP.items():
                if key in upper and len(upper) < 60:
                    if roman in INCLUDED_SECTIONS:
                        current_section = roman
                        current_section_name = text.strip()
                    else:
                        current_section = None
                    break

            if current_section is None:
                continue

            # Department / organism rows
            if row.name in ("tr", "div") and not row.find("a"):
                if len(text) > 3 and len(text) < 120:
                    current_organism = text

            link = row.find("a", href=True)
            if not link:
                continue

            href = link["href"]
            if ".pdf" not in href.lower() and "document" not in href.lower():
                continue

            title = link.get_text(strip=True)
            pdf_url = href if href.startswith("http") else BASE_URL + href
            act_id = re.search(r"\d{4}/\d+", href)
            act_id = act_id.group(0).replace("/", "-") if act_id else href.split("/")[-1]

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id="DOGC-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[DOGC] Found %d acts in sections I/III", len(acts))
        return acts
