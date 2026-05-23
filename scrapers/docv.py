"""DOCV — Diari Oficial de la Comunitat Valenciana.

El portal usa una SPA JavaScript, pero los XMLs están disponibles en:
  https://dogv.gva.es/datos/{YYYY}/{MM}/{DD}/xml/
Se intenta un directory listing; si falla se registra un aviso.
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://dogv.gva.es"
XML_DIR_URL = "https://dogv.gva.es/datos/{year}/{month}/{day}/xml/"

SECTION_MAP = {
    "DISPOSICIONS GENERALS": "I",
    "DISPOSICIONES GENERALES": "I",
    "ALTRES DISPOSICIONS": "III",
    "OTRAS DISPOSICIONES": "III",
}


class DOCVScraper(BaseScraper):
    bulletin_id = "DOCV"
    bulletin_name = "Diari Oficial de la Comunitat Valenciana"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[DOCV] Fetching sumario for %s", target_date.isoformat())

        dir_url = XML_DIR_URL.format(
            year=target_date.strftime("%Y"),
            month=target_date.strftime("%m"),
            day=target_date.strftime("%d"),
        )
        resp = self._safe_get(dir_url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        xml_links = [
            (a["href"] if a["href"].startswith("http") else BASE_URL + a["href"])
            for a in soup.find_all("a", href=re.compile(r"\.xml$", re.I))
        ]

        if not xml_links:
            logger.warning("[DOCV] No XML files found at %s", dir_url)
            return []

        acts: list[Act] = []
        for xml_url in xml_links:
            acts.extend(self._parse_xml(xml_url, target_date.isoformat()))

        logger.info("[DOCV] Found %d acts in sections I/III", len(acts))
        return acts

    def _parse_xml(self, url: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        resp = self._safe_get(url)
        if resp is None:
            return acts

        try:
            soup = BeautifulSoup(resp.content, "lxml-xml")
        except Exception:
            soup = BeautifulSoup(resp.text, "lxml")

        current_section = None
        current_section_name = ""
        current_organism = ""

        for tag in soup.find_all(True):
            text = tag.get_text(strip=True)
            upper = text.upper()

            for key, roman in SECTION_MAP.items():
                if key in upper and len(upper) < 80:
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()
                    break
            else:
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV)\b", upper)
                if sec_match and len(upper) < 80:
                    roman = sec_match.group(1)
                    current_section = roman if roman in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()

            if current_section is None:
                continue

            # Look for PDF URL attributes or child text elements
            pdf_url = tag.get("urlPdf") or tag.get("url_pdf") or ""
            if not pdf_url:
                pdf_tag = tag.find(re.compile(r"url.?pdf", re.I))
                if pdf_tag:
                    pdf_url = pdf_tag.get_text(strip=True)

            if not pdf_url:
                continue

            if not pdf_url.startswith("http"):
                pdf_url = BASE_URL + pdf_url

            title_tag = tag.find(re.compile(r"titulo|titol", re.I))
            title = title_tag.get_text(strip=True) if title_tag else text[:200]
            act_id = tag.get("id") or tag.get("identificador") or pdf_url.split("/")[-1]

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id="DOCV-" + str(act_id),
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
