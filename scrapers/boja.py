"""BOJA — Boletín Oficial de la Junta de Andalucía.

Two-step scrape:
  1. Calendar page: https://www.juntadeandalucia.es/eboja/{YYYYMMDD}.html
     → links to bulletin at relative path like "2026/97/"
  2. Bulletin page: https://www.juntadeandalucia.es/eboja/2026/97/
     → contains <h2>1. Disposiciones generales</h2> + PDF links
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.juntadeandalucia.es"
CALENDAR_URL = "https://www.juntadeandalucia.es/eboja/{datestr}.html"
EBOJA_BASE = "https://www.juntadeandalucia.es/eboja/"

# BOJA uses numeric section prefixes: "1. Disposiciones generales" → I
SECTION_MAP = {
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "6": "VI",
}


class BOJAScraper(BaseScraper):
    bulletin_id = "BOJA"
    bulletin_name = "Boletín Oficial de la Junta de Andalucía"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOJA] Fetching sumario for %s", target_date.isoformat())

        # Step 1: get calendar page to find bulletin URL
        calendar_url = CALENDAR_URL.format(datestr=target_date.strftime("%Y%m%d"))
        resp = self._safe_get(calendar_url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_url = self._find_boletin_link(soup)
        if not boletin_url:
            logger.warning("[BOJA] No boletín link found for %s", target_date.isoformat())
            return []

        # Step 2: fetch actual bulletin page
        resp2 = self._safe_get(boletin_url)
        if resp2 is None:
            return []

        soup2 = BeautifulSoup(resp2.text, "lxml")
        return self._parse(soup2, target_date.isoformat(), boletin_url)

    def _find_boletin_link(self, soup: BeautifulSoup) -> Optional[str]:
        """Find the actual bulletin URL from the calendar page."""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Relative links like "2026/97/" that go to the bulletin
            if re.match(r"^\d{4}/\d+/$", href):
                return EBOJA_BASE + href
            # Absolute paths like "/eboja/2026/97/"
            m = re.search(r"/eboja/(\d{4}/\d+/?)$", href)
            if m:
                return href if href.startswith("http") else BASE_URL + href
        return None

    def _parse(self, soup: BeautifulSoup, pub_date: str, boletin_url: str) -> list[Act]:
        acts: list[Act] = []
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            # BOJA section headers: "1. Disposiciones generales", "3. Otras disposiciones"
            m = re.match(r"^(\d+)\.\s+(.+)$", text.strip())
            if m and len(text) < 80:
                num = m.group(1)
                roman = SECTION_MAP.get(num, "")
                if roman:
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()
                    current_organism = ""
                    continue

            # Also match standard "SECCIÓN I/III" format
            sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
            if sec_match:
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                continue

            if current_section is None:
                continue

            if tag.name in ("h3", "h4", "p") and not tag.find("a"):
                # Potential organism header
                if text and not re.search(r"\.pdf", text, re.I):
                    current_organism = text
                    continue

            link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            if not link:
                continue

            href = link["href"]
            if href.startswith("http"):
                pdf_url = href
            elif href.startswith("/"):
                pdf_url = BASE_URL + href
            else:
                # Relative to bulletin page URL (e.g. "BOJA26-097-00003-6801-01.pdf")
                pdf_url = boletin_url.rstrip("/") + "/" + href

            title = link.get_text(strip=True) or text
            # PDF file name is often the act id pattern
            act_id = re.search(r"BOJA\d+-\d+-\d+[-\w]*", pdf_url, re.I)
            act_id = act_id.group(0).upper() if act_id else pdf_url.split("/")[-1].replace(".pdf", "")

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
