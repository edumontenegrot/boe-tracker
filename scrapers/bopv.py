"""BOPV — Boletín Oficial del País Vasco.

Los ficheros .shtml tienen nombres no predecibles desde la fecha.
Se obtiene el enlace al boletín del día scrapeando la página de inicio.
  https://www.euskadi.eus/bopv2/
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.euskadi.eus"
HOME_URL = "https://www.euskadi.eus/bopv2/"


class BOPVScraper(BaseScraper):
    bulletin_id = "BOPV"
    bulletin_name = "Boletín Oficial del País Vasco"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOPV] Fetching sumario for %s", target_date.isoformat())

        resp = self._safe_get(HOME_URL)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_url = self._find_date_link(soup, target_date)
        if not boletin_url:
            logger.warning("[BOPV] No boletín link found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_url, target_date.isoformat())

    def _find_date_link(self, soup: BeautifulSoup, target_date: date) -> Optional[str]:
        """Find the link whose visible text matches the target date."""
        # Euskadi shows dates like "2026/05/22" or "22/05/2026"
        patterns = [
            target_date.strftime("%Y/%m/%d"),
            target_date.strftime("%d/%m/%Y"),
            target_date.strftime("%Y%m%d"),
        ]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            for p in patterns:
                if p in href or p in text:
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

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "td"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            sec_match = re.search(
                r"(?:APARTADO|SECCI[OÓ]N|ATAL)\s+(I{1,3}V?|IV|VI{0,3})\b", upper
            )
            if sec_match:
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                continue

            num_match = re.match(r"^(\d)\.\s+", text)
            if num_match:
                n2r = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}
                roman = n2r.get(num_match.group(1), "")
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                continue

            if current_section is None:
                continue

            link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            if not link:
                continue

            href = link["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True) or text
            act_id = "BOPV-" + pdf_url.split("/")[-1].replace(".pdf", "")

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id=act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism="",
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[BOPV] Found %d acts in sections I/III", len(acts))
        return acts
