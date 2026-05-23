"""BOC — Boletín Oficial de Canarias.

Los boletines se acceden por número de issue, no por fecha.
Se scrapea la portada para resolver fecha → número de issue.
  Portada: https://www.gobiernodecanarias.org/boc/
  Issue:   https://www.gobiernodecanarias.org/boc/{YYYY}/{NNN}/
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gobiernodecanarias.org"
HOME_URL = "https://www.gobiernodecanarias.org/boc/"


class BOCScraper(BaseScraper):
    bulletin_id = "BOC"
    bulletin_name = "Boletín Oficial de Canarias"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOC] Fetching sumario for %s", target_date.isoformat())

        resp = self._safe_get(HOME_URL)
        if resp is None:
            return []

        # BOC serves UTF-8 but doesn't declare charset — force correct decoding
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")
        boletin_url = self._find_date_link(soup, target_date)
        if not boletin_url:
            logger.warning("[BOC] No boletín found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_url, target_date.isoformat())

    def _find_date_link(self, soup: BeautifulSoup, target_date: date) -> Optional[str]:
        """Find the issue URL for the given date from the homepage."""
        # Homepage lists recent issues with links like /boc/2026/098 (no trailing slash)
        year_str = target_date.strftime("%Y")
        # Spanish month names for matching link text
        MESES = ["enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        day_str = str(target_date.day)
        month_name = MESES[target_date.month - 1]
        year_full = target_date.strftime("%Y")
        date_patterns = [
            target_date.strftime("%Y%m%d"),
            target_date.strftime("%d/%m/%Y"),
            f"{day_str} de {month_name} de {year_full}",
        ]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Match links like /boc/2026/098 or /boc/2026/098/
            if not re.search(rf"/boc/{year_str}/\d+", href):
                continue
            full_text = a.get_text(" ", strip=True)
            if a.parent:
                full_text += " " + a.parent.get_text(" ", strip=True)
            for p in date_patterns:
                if p.lower() in full_text.lower():
                    return href if href.startswith("http") else BASE_URL + href
        return None

    def _parse_boletin(self, url: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        resp = self._safe_get(url)
        if resp is None:
            return acts

        resp.encoding = "utf-8"   # BOC serves UTF-8 without declaring it
        soup = BeautifulSoup(resp.text, "lxml")
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "td"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            section_detected = False
            # BOC section headers: "I. Disposiciones generales", "III. Otras Resoluciones"
            m = re.match(r"^(I{1,3}V?|IV|VI{0,3})\.\s+[A-ZÁÉÍÓÚ]", upper)
            if m and len(text) < 80:
                roman = m.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True
            elif re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper):
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True
            elif re.search(r"DISPOSICIONES\s+GENERALES", upper) and len(text) < 80:
                current_section = "I"
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True
            elif re.search(r"OTRAS\s+(DISPOSICIONES|RESOLUCIONES)", upper) and len(text) < 80:
                current_section = "III"
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True

            if section_detected:
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
            act_id = "BOC-" + pdf_url.split("/")[-1].replace(".pdf", "")

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

        logger.info("[BOC] Found %d acts in sections I/III", len(acts))
        return acts
