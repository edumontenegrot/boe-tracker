"""DOGA — Diario Oficial de Galicia.

Secciones por separado (Galicia publica una URL por sección):
  https://www.xunta.gal/diario-oficial-galicia/mostrarContenido.do
    ?paginaCompleta=true&idEstado=5&rutaRelativa=true
    &ruta=/{YYYY}/{YYYYMMDD}/Secciones{N}_gl.html

N=1 → Sección I (Disposicións xerais)
N=3 → Sección III (Outras disposicións)
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.xunta.gal"
SECTION_URL = (
    "https://www.xunta.gal/diario-oficial-galicia/mostrarContenido.do"
    "?paginaCompleta=true&idEstado=5&rutaRelativa=true"
    "&ruta=/{year}/{datestr}/Secciones{n}_gl.html"
)

# Map section number N in the URL to roman numeral
SECTION_N_MAP = {"1": "I", "3": "III"}


class DOGAScraper(BaseScraper):
    bulletin_id = "DOGA"
    bulletin_name = "Diario Oficial de Galicia"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        year = target_date.strftime("%Y")
        datestr = target_date.strftime("%Y%m%d")
        logger.info("[DOGA] Fetching sumario for %s", target_date.isoformat())

        acts: list[Act] = []
        for n, roman in SECTION_N_MAP.items():
            url = SECTION_URL.format(year=year, datestr=datestr, n=n)
            resp = self._safe_get(url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            acts.extend(self._parse_section(soup, roman, target_date.isoformat()))

        logger.info("[DOGA] Found %d acts in sections I/III", len(acts))
        return acts

    def _parse_section(self, soup: BeautifulSoup, roman: str, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        section_name = "Disposicións xerais" if roman == "I" else "Outras disposicións"
        current_organism = ""

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div", "td"]):
            text = tag.get_text(strip=True)

            if tag.name in ("h3", "h4") and not tag.find("a"):
                current_organism = text
                continue

            link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            if not link:
                continue

            href = link["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True) or text
            act_id = "DOGA-" + pdf_url.split("/")[-1].replace(".pdf", "")

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id=act_id,
                title=title,
                section=roman,
                section_name=section_name,
                rank="",
                organism=current_organism,
                pdf_url=pdf_url,
                summary="",
                pub_date=pub_date,
            ))

        return acts
