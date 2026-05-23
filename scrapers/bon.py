"""BON — Boletín Oficial de Navarra.

Sumario: https://bon.navarra.es/es/boletin/-/sumario/{YYYYMMDD}

The BON uses a numeric subsection scheme: "1.1. Disposiciones", "1.3. Convenios…"
Individual acts link to detail pages (/anuncio/-/texto/{year}/{num}/{N}), not PDFs.
We collect acts with the detail page as the pdf_url (PDFs are not individually exposed).

Sections:
  1.1 / 1.1. Leyes y Decretos Forales  → I  (Disposiciones generales)
  1.3 / 1.5 type subsections            → III (Otras disposiciones - best effort)
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://bon.navarra.es"
SUMARIO_URL = "https://bon.navarra.es/es/boletin/-/sumario/{datestr}"

# BON subsections that map to Section I (Disposiciones generales)
SECTION_I_PATTERNS = [
    r"1\.1\.",          # 1.1. Leyes y Decretos Forales / Disposiciones con Fuerza de Ley
    r"LEYES Y DECRETOS",
    r"DISPOSICIONES CON FUERZA DE LEY",
    r"DISPOSICIONES GENERALES",
]

# BON subsections that map to Section III (Otras disposiciones)
SECTION_III_PATTERNS = [
    r"1\.3\.",          # 1.3. Ordenanzas, Reglamentos
    r"1\.5\.",          # 1.5. Convenios y acuerdos
    r"1\.6\.",          # 1.6. Anuncios de empleo / resoluciones
    r"OTRAS DISPOSICIONES",
    r"CONVENIOS",
    r"ORDENANZAS",
]


def _detect_bon_section(text: str) -> Optional[str]:
    upper = text.upper()
    for pat in SECTION_I_PATTERNS:
        if re.search(pat, upper):
            return "I"
    for pat in SECTION_III_PATTERNS:
        if re.search(pat, upper):
            return "III"
    return None


class BONScraper(BaseScraper):
    bulletin_id = "BON"
    bulletin_name = "Boletín Oficial de Navarra"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        url = SUMARIO_URL.format(datestr=target_date.strftime("%Y%m%d"))
        logger.info("[BON] Fetching sumario for %s", target_date.isoformat())

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

        for tag in soup.find_all(["h2", "h3", "h4", "p", "li", "div"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            # Detect section heading
            if len(text) < 100:
                detected = _detect_bon_section(text)
                if detected is not None:
                    current_section = detected if detected in INCLUDED_SECTIONS else None
                    current_section_name = text.strip()
                    current_organism = ""
                    continue

            if current_section is None:
                continue

            if tag.name in ("h3", "h4") and not tag.find("a"):
                current_organism = text
                continue

            # BON acts link to /anuncio/-/texto/{year}/{num}/{N}
            link = tag.find("a", href=re.compile(r"/anuncio/-/texto/\d{4}/\d+/\d+", re.I))
            if not link:
                # Also check for direct PDF links (rare)
                link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            if not link:
                continue

            href = link["href"]
            act_url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True) or text

            # Use the act detail URL as the act_id base
            m = re.search(r"/anuncio/-/texto/(\d{4}/\d+/\d+)", href)
            if m:
                act_id = "BON-" + m.group(1).replace("/", "-")
            else:
                act_id = "BON-" + href.split("/")[-1]

            acts.append(Act(
                bulletin_id=self.bulletin_id,
                act_id=act_id,
                title=title,
                section=current_section,
                section_name=current_section_name,
                rank="",
                organism=current_organism,
                pdf_url=act_url,   # detail page URL (no individual PDFs exposed)
                summary="",
                pub_date=pub_date,
            ))

        logger.info("[BON] Found %d acts in sections I/III", len(acts))
        return acts
