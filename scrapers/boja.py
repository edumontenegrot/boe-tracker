"""BOJA — Boletín Oficial de la Junta de Andalucía.

Sumario: https://www.juntadeandalucia.es/boja/boletines/{YYYY}/{NN}/index.html
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.juntadeandalucia.es"
INDEX_URL = "https://www.juntadeandalucia.es/boja/buscador"


class BOJAScraper(BaseScraper):
    bulletin_id = "BOJA"
    bulletin_name = "Boletín Oficial de la Junta de Andalucía"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOJA] Fetching sumario for %s", target_date.isoformat())

        # Search for the bulletin number for this date
        params = {
            "fechaDesde": target_date.strftime("%d/%m/%Y"),
            "fechaHasta": target_date.strftime("%d/%m/%Y"),
        }
        resp = self._safe_get(INDEX_URL, params=params)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_url = self._find_boletin_url(soup)
        if not boletin_url:
            logger.warning("[BOJA] No boletín found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_url, target_date.isoformat())

    def _find_boletin_url(self, soup: BeautifulSoup) -> Optional[str]:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/boja/boletines/" in href or "sumario" in href.lower():
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

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            # Section detection
            sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3}|IX|XI{0,3})\b", upper)
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

            # Organism / department heading
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
            act_id = re.search(r"BOJA\d+-\d+-\d+", pdf_url, re.I)
            act_id = act_id.group(0) if act_id else pdf_url.split("/")[-1].replace(".pdf", "")

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

        logger.info("[BOJA] Found %d acts in sections I/III", len(acts))
        return acts
