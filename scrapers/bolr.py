"""BOC Cantabria — Boletín Oficial de Cantabria.

Requiere POST (no GET) al endpoint:
  https://boc.cantabria.es/boces/inicioCargaInicialBoletines.do
  form data: strFechaDeseada={DD/MM/YYYY}&tipoBoletin=O
"""

import logging
import re
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://boc.cantabria.es"
POST_URL = "https://boc.cantabria.es/boces/inicioCargaInicialBoletines.do"


class BOLRScraper(BaseScraper):
    bulletin_id = "BOC-CANT"
    bulletin_name = "Boletín Oficial de Cantabria"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOC-CANT] Fetching sumario for %s", target_date.isoformat())

        try:
            resp = self.session.post(
                POST_URL,
                data={
                    "strFechaDeseada": target_date.strftime("%d/%m/%Y"),
                    "tipoBoletin": "O",
                },
                timeout=(10, 30),
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("[BOC-CANT] POST failed: %s", exc)
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
            act_id = "BOC-CANT-" + pdf_url.split("/")[-1].replace(".pdf", "")

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

        logger.info("[BOC-CANT] Found %d acts in sections I/III", len(acts))
        return acts
