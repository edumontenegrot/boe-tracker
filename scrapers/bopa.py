"""BOPA — Boletín Oficial del Principado de Asturias.

Dominio migrado a miprincipado.asturias.es (Liferay portal).
URL: https://miprincipado.asturias.es/bopa-sumario
  ?p_p_id=pa_sede_bopa_web_portlet_SedeBopaSummaryWeb
  &p_p_lifecycle=0&p_p_state=normal&p_p_mode=view
  &p_r_p_summaryDate={DD/MM/YYYY}&p_r_p_summaryIsSearch=false
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://miprincipado.asturias.es"
SUMARIO_URL = (
    "https://miprincipado.asturias.es/bopa-sumario"
    "?p_p_id=pa_sede_bopa_web_portlet_SedeBopaSummaryWeb"
    "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
    "&p_r_p_summaryDate={date_str}&p_r_p_summaryIsSearch=false"
)


class BOPAScraper(BaseScraper):
    bulletin_id = "BOPA"
    bulletin_name = "Boletín Oficial del Principado de Asturias"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        url = SUMARIO_URL.format(date_str=target_date.strftime("%d/%m/%Y"))
        logger.info("[BOPA] Fetching sumario for %s", target_date.isoformat())

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

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "td"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
            if sec_match:
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                continue

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
            act_id = "BOPA-" + pdf_url.split("/")[-1].replace(".pdf", "")

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

        logger.info("[BOPA] Found %d acts in sections I/III", len(acts))
        return acts
