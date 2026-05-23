"""DOE — Diario Oficial de Extremadura.

Sumario: https://doe.juntaex.es/pdfs/doe/{YYYY}/{MM}/{DD}/doe{YYYYMMDD}.pdf  (PDF directo)
Buscador HTML: https://doe.juntaex.es/ccreadop/sumariocopia.html?fecha={YYYYMMDD}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://doe.juntaex.es"
SUMARIO_URL = "https://doe.juntaex.es/ccreadop/sumariocopia.html"


class DOEScraper(BaseScraper):
    bulletin_id = "DOE"
    bulletin_name = "Diario Oficial de Extremadura"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[DOE] Fetching sumario for %s", target_date.isoformat())

        date_str = target_date.strftime("%Y%m%d")
        resp = self._safe_get(SUMARIO_URL, params={"fecha": date_str})
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse(soup, target_date.isoformat(), date_str)

    def _parse(self, soup: BeautifulSoup, pub_date: str, date_str: str) -> list[Act]:
        acts: list[Act] = []
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "tr", "td"]):
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
                act_id="DOE-" + act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[DOE] Found %d acts in sections I/III", len(acts))
        return acts
