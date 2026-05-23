"""BOPA — Boletín Oficial del Principado de Asturias.

Dominio migrado a miprincipado.asturias.es (Liferay portal).
URL: https://miprincipado.asturias.es/bopa-sumario
  ?p_p_id=pa_sede_bopa_web_portlet_SedeBopaSummaryWeb
  &p_p_lifecycle=0&p_p_state=normal&p_p_mode=view
  &p_r_p_summaryDate={DD/MM/YYYY}&p_r_p_summaryIsSearch=false

HTML structure:
  <h4>I. Principado de Asturias</h4>
    <h5>AUTORIDADES Y PERSONAL</h5>       ← skip
    <h5>OTRAS DISPOSICIONES</h5>          ← Section III
      <h6>CONSEJERÍA DE X</h6>            ← organism
      <p class="subAuthor">INSTITUTO Y</p> ← sub-organism
      <dl>
        <dt>Title text [Cód. 2026-NNNNN]</dt>
        <dd>
          <a href="...">Texto...</a>
          <span class="pdfResultadoBopa">
            <a href="/bopa/YYYY/MM/DD/2026-NNNNN.pdf">PDF</a>(NKB)
          </span>
        </dd>
      </dl>
    <h5>ANUNCIOS</h5>                     ← skip
  <h4>IV. Administración Local</h4>       ← skip
"""

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://miprincipado.asturias.es"
SUMARIO_URL = (
    "https://miprincipado.asturias.es/bopa-sumario"
    "?p_p_id=pa_sede_bopa_web_portlet_SedeBopaSummaryWeb"
    "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
    "&p_r_p_summaryDate={date_str}&p_r_p_summaryIsSearch=false"
)


class BOPAScraper(BaseScraper):
    bulletin_id = "BOPA"
    bulletin_name = "Boletín Oficial del Principado de Asturias"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        url = SUMARIO_URL.format(date_str=target_date.strftime("%d/%m/%Y"))
        logger.info("[BOPA] Fetching sumario for %s", target_date.isoformat())

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

        # Walk the document in order, using all structural elements
        for tag in soup.find_all(["h2", "h3", "h4", "h5", "h6", "p", "dl"]):
            text = tag.get_text(strip=True)
            upper = text.upper()

            # ── Section detection ──────────────────────────────────────
            section_detected = False

            # <h4>I. Principado de Asturias</h4>  /  <h4>IV. Administración Local</h4>
            m_roman = re.match(r"^(I{1,3}V?|IV|VI{0,3})\.\s+[A-ZÁÉÍÓÚ]", upper)
            if m_roman and len(text) < 80 and tag.name in ("h2", "h3", "h4"):
                roman = m_roman.group(1)
                # This sets the TOP-LEVEL section; acts are further filtered by h5 subsection
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True

            # <h5>OTRAS DISPOSICIONES</h5>  → subsection maps to III
            elif tag.name == "h5" and re.search(r"OTRAS\s+DISPOSICIONES", upper) and len(text) < 80:
                current_section = "III"
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True

            # <h5>DISPOSICIONES GENERALES</h5>  → subsection maps to I
            elif tag.name == "h5" and re.search(r"DISPOSICIONES\s+GENERALES", upper) and len(text) < 80:
                current_section = "I"
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True

            # Other h5 subsections to explicitly skip
            elif tag.name == "h5" and upper in (
                "AUTORIDADES Y PERSONAL", "ANUNCIOS", "OTROS ANUNCIOS",
                "OPOSICIONES Y CONCURSOS", "CONTRATACIÓN", "SUBVENCIONES",
            ):
                current_section = None
                section_detected = True

            # Generic SECCIÓN N pattern
            elif re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper):
                sec_match = re.search(r"SECCI[OÓ]N\s+(I{1,3}V?|IV|VI{0,3})\b", upper)
                roman = sec_match.group(1)
                current_section = roman if roman in INCLUDED_SECTIONS else None
                current_section_name = text.strip()
                current_organism = ""
                section_detected = True

            if section_detected:
                continue

            if current_section is None:
                continue

            # ── Organism update ───────────────────────────────────────
            if tag.name == "h6" and not tag.find("a"):
                current_organism = text
                continue

            # <p class="subAuthor"> is a sub-organism label
            if tag.name == "p" and "subAuthor" in (tag.get("class") or []):
                current_organism = text
                continue

            # ── Act extraction ────────────────────────────────────────
            # Acts live in <dl> elements: title in <dt>, PDF in <dd>
            if tag.name != "dl":
                continue

            dt = tag.find("dt")
            title = dt.get_text(strip=True) if dt else text

            # Remove trailing "[Cód. XXXX-NNNNN]" from title
            title = re.sub(r"\s*\[Cód\.[^\]]*\]\s*$", "", title).strip()

            # PDF link is in <span class="pdfResultadoBopa"> <a>
            pdf_span = tag.find("span", class_="pdfResultadoBopa")
            if pdf_span:
                link = pdf_span.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            else:
                link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            if not link:
                continue

            href = link["href"]
            pdf_url = href if href.startswith("http") else BASE_URL + href
            act_id = "BOPA-" + pdf_url.split("/")[-1].replace(".pdf", "")

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

        logger.info("[BOPA] Found %d acts in sections I/III", len(acts))
        return acts
