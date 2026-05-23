"""DOGC — Diari Oficial de la Generalitat de Catalunya.

Buscador: https://dogc.gencat.cat/ca/inici/resultats/index.html
  ?orderBy=3&page=1&typeSearch=1&advanced=true&current=false
  &publicationDateInitial=0
  &datePublicationFrom={DD/MM/YYYY}&datePublicationTo={DD/MM/YYYY}
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://dogc.gencat.cat"
SEARCH_URL = "https://dogc.gencat.cat/ca/inici/resultats/index.html"

SECTION_MAP = {
    "DISPOSICIONS GENERALS": "I",
    "DISPOSICIONES GENERALES": "I",
    "ALTRES DISPOSICIONS": "III",
    "OTRAS DISPOSICIONES": "III",
}


class DOGCScraper(BaseScraper):
    bulletin_id = "DOGC"
    bulletin_name = "Diari Oficial de la Generalitat de Catalunya"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        date_str = target_date.strftime("%d/%m/%Y")
        logger.info("[DOGC] Fetching sumario for %s", target_date.isoformat())

        params = {
            "orderBy": "3",
            "page": "1",
            "typeSearch": "1",
            "advanced": "true",
            "current": "false",
            "publicationDateInitial": "0",
            "datePublicationFrom": date_str,
            "datePublicationTo": date_str,
        }
        resp = self._safe_get(SEARCH_URL, params=params)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        # Each result links to a detail page; collect and parse each one
        detail_links = self._find_detail_links(soup)
        if not detail_links:
            logger.warning("[DOGC] No results found for %s", target_date.isoformat())
            return []

        acts: list[Act] = []
        for link_url in detail_links:
            acts.extend(self._parse_detail(link_url, target_date.isoformat()))

        logger.info("[DOGC] Found %d acts in sections I/III", len(acts))
        return acts

    def _find_detail_links(self, soup: BeautifulSoup) -> list[str]:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/ca/document-del-dogc/" in href or "/ca/inici/resultats/detall/" in href:
                full = href if href.startswith("http") else BASE_URL + href
                if full not in links:
                    links.append(full)
        return links

    def _parse_detail(self, url: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        resp = self._safe_get(url)
        if resp is None:
            return acts

        soup = BeautifulSoup(resp.text, "lxml")
        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div", "td"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            for key, roman in SECTION_MAP.items():
                if key in upper and len(upper) < 80:
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()
                    break
            else:
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV)\b", upper)
                if sec_match:
                    roman = sec_match.group(1)
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()

            if current_section is None:
                continue

            if tag.name in ("h3", "h4") and not tag.find("a"):
                current_organism = text
                continue

            link = tag.find("a", href=re.compile(r"\.pdf$", re.I))
            if not link:
                continue

            href = link["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True) or text
            act_id = re.search(r"\d{4}/\d+", href)
            act_id = "DOGC-" + act_id.group(0).replace("/", "-") if act_id else "DOGC-" + href.split("/")[-1]

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

        return acts
