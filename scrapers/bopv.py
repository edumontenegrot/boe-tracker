"""BOPV — Boletín Oficial del País Vasco.

Sumario: https://www.euskadi.eus/bopv2/datos/{YYYY}/{MM}/{YYYYMMDD}.shtml
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.euskadi.eus"
SUMARIO_URL = "https://www.euskadi.eus/bopv2/datos/{year}/{month}/{datestr}.shtml"


class BOPVScraper(BaseScraper):
    bulletin_id = "BOPV"
    bulletin_name = "Boletín Oficial del País Vasco"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        url = SUMARIO_URL.format(
            year=target_date.strftime("%Y"),
            month=target_date.strftime("%m"),
            datestr=target_date.strftime("%Y%m%d"),
        )
        logger.info("[BOPV] Fetching sumario for %s", target_date.isoformat())

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

        for tag in soup.find_all(["h2", "h3", "h4", "li", "div", "p"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            sec_match = re.search(
                r"(?:APARTADO|SECCI[OÓ]N|ATAL)\s+(I{1,3}V?|IV|VI{0,3})\b", upper
            )
            if sec_match:
                roman = sec_match.group(1)
                if roman in INCLUDED_SECTIONS:
                    current_section = roman
                    current_section_name = text.strip()
                else:
                    current_section = None
                current_organism = ""
                continue

            # BOPV labels sections with numbers 1–5
            num_match = re.match(r"^(\d)\.\s+", text)
            if num_match:
                num_to_roman = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}
                roman = num_to_roman.get(num_match.group(1), "")
                if roman in INCLUDED_SECTIONS:
                    current_section = roman
                    current_section_name = text.strip()
                else:
                    current_section = None
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
            act_id = re.search(r"\d{4}\d{4}\d+", pdf_url)
            act_id = "BOPV-" + act_id.group(0) if act_id else "BOPV-" + pdf_url.split("/")[-1]

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

        logger.info("[BOPV] Found %d acts in sections I/III", len(acts))
        return acts
