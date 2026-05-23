"""BOCM — Boletín Oficial de la Comunidad de Madrid.

Sumario: https://www.bocm.es/boletin/buscador?fecha={DD/MM/YYYY}
Nota: el servidor de bocm.es tiene un cert SSL defectuoso; se usa verify=False.
"""

import logging
import re
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.bocm.es"
SEARCH_URL = "https://www.bocm.es/boletin/buscador"


class BOCMScraper(BaseScraper):
    bulletin_id = "BOCM"
    bulletin_name = "Boletín Oficial de la Comunidad de Madrid"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        date_str = target_date.strftime("%d/%m/%Y")
        logger.info("[BOCM] Fetching sumario for %s", target_date.isoformat())

        # verify=False porque bocm.es tiene cert SSL inválido
        try:
            resp = self.session.get(
                SEARCH_URL,
                params={"fecha": date_str},
                timeout=(10, 30),
                verify=False,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("[BOCM] Request failed: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        boletin_link = self._find_boletin_link(soup, target_date)
        if not boletin_link:
            logger.warning("[BOCM] No boletín link found for %s", target_date.isoformat())
            return []

        return self._parse_boletin(boletin_link, target_date.isoformat())

    def _find_boletin_link(self, soup: BeautifulSoup, target_date: date) -> Optional[str]:
        date_pattern = target_date.strftime("%Y%m%d")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if date_pattern in href and "bocm" in href.lower():
                return href if href.startswith("http") else BASE_URL + href
        # Fallback: any link that looks like a bulletin
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"bocm[-_]\d{8}", href, re.I):
                return href if href.startswith("http") else BASE_URL + href
        return None

    def _parse_boletin(self, url: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        try:
            resp = self.session.get(url, timeout=(10, 30), verify=False)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("[BOCM] Failed to fetch bulletin page: %s", exc)
            return acts

        soup = BeautifulSoup(resp.text, "lxml")
        current_section = None
        current_section_name = ""

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
            if sec_match:
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                continue

            if current_section is None:
                continue

            link = tag.find("a", href=re.compile(r"\.pdf$", re.I))
            if not link:
                continue

            href = link["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True) or text
            act_id = re.search(r"BOCM-\d{8}-\d+", pdf_url, re.I)
            act_id = act_id.group(0).upper() if act_id else pdf_url.split("/")[-1].replace(".pdf", "")

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

        logger.info("[BOCM] Found %d acts in sections I/III", len(acts))
        return acts
