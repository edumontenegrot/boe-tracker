"""DOCM — Diario Oficial de Castilla-La Mancha.

URL: https://docm.jccm.es/docm/cambiarBoletin.do?fecha={YYYYMMDD}

Section headers: "I.- DISPOSICIONES GENERALES", "III.- OTRAS DISPOSICIONES Y ACTOS"
PDF links:       ./descargarArchivo.do?ruta=2026/05/22/pdf/2026_3899.pdf&tipo=rutaDocm
"""

import logging
import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://docm.jccm.es"
DOCM_BASE = "https://docm.jccm.es/docm/"
SUMARIO_URL = "https://docm.jccm.es/docm/cambiarBoletin.do"


class DOCMScraper(BaseScraper):
    bulletin_id = "DOCM"
    bulletin_name = "Diario Oficial de Castilla-La Mancha"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[DOCM] Fetching sumario for %s", target_date.isoformat())

        resp = self._safe_get(
            SUMARIO_URL,
            params={"fecha": target_date.strftime("%Y%m%d")},
        )
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

            section_detected = False
            # DOCM format: "I.- DISPOSICIONES GENERALES", "III.- OTRAS DISPOSICIONES Y ACTOS"
            m = re.match(r"^(I{1,3}V?|IV|VI{0,3})\.-\s*(.+)$", upper)
            if m and len(text) < 80:
                roman = m.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True
            # Also standard "SECCIÓN I/III" format
            elif re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper):
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True
            # Keywords: "DISPOSICIONES GENERALES" and "OTRAS DISPOSICIONES"
            elif re.search(r"DISPOSICIONES\s+GENERALES", upper) and len(text) < 80:
                current_section = "I"
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True
            elif re.search(r"OTRAS\s+DISPOSICIONES", upper) and len(text) < 80:
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

            # PDF links: end in .pdf OR are descargarArchivo.do URLs
            link = (
                tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
                or tag.find("a", href=re.compile(r"descargarArchivo\.do", re.I))
            )
            if not link:
                continue

            href = link["href"]
            # Resolve relative to the DOCM base
            if href.startswith("./") or href.startswith("descargarArchivo"):
                href = href.lstrip("./")
                pdf_url = DOCM_BASE + href
            elif href.startswith("/"):
                pdf_url = BASE_URL + href
            elif href.startswith("http"):
                pdf_url = href
            else:
                pdf_url = DOCM_BASE + href

            title = link.get_text(strip=True) or text
            # Extract act id from the ruta parameter if present
            ruta_match = re.search(r"ruta=([^&]+)", pdf_url)
            if ruta_match:
                ruta = ruta_match.group(1).replace("%2F", "/")
                act_id = "DOCM-" + ruta.split("/")[-1].replace(".pdf", "")
            else:
                act_id = "DOCM-" + pdf_url.split("/")[-1].split("?")[0].replace(".pdf", "")

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

        logger.info("[DOCM] Found %d acts in sections I/III", len(acts))
        return acts
