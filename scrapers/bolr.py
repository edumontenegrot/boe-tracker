"""BOC Cantabria — Boletín Oficial de Cantabria.

Two-step approach:
  1. GET https://boc.cantabria.es/boces/menu.do?dir=/inicioCargaInicialBoletines.do
     → establishes JSESSIONID cookie
  2. POST https://boc.cantabria.es/boces/boletines.do
     form: boletinBean.fecBolString={DD/MM/YYYY}&boletinBean.tipoBol=0&boton=Buscar

HTML structure:
  <span class="titulo2">1.Disposiciones Generales</span>
  <span class="spanH4">Ayuntamiento de X</span>
  <p>Title of the act...</p>
  <div class="enlacesDoc">
    <div class="tipoPDFanuncio">
      <a href="verAnuncioAction.do?idAnuBlob=NNN">PDF (BOC-...)</a>
    </div>
  </div>
"""

import logging
import re
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

BASE_URL = "https://boc.cantabria.es"
MENU_URL = "https://boc.cantabria.es/boces/menu.do?dir=/inicioCargaInicialBoletines.do"
POST_URL = "https://boc.cantabria.es/boces/boletines.do"

ANUNCIO_RE = re.compile(r"verAnuncioAction\.do\?idAnuBlob=(\d+)", re.I)


class BOLRScraper(BaseScraper):
    bulletin_id = "BOC-CANT"
    bulletin_name = "Boletín Oficial de Cantabria"
    base_url = BASE_URL

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        logger.info("[BOC-CANT] Fetching sumario for %s", target_date.isoformat())

        # Step 1: GET menu page to establish JSESSIONID session cookie
        r0 = self._safe_get(MENU_URL)
        if r0 is None:
            return []

        # Step 2: POST search form to boletines.do
        try:
            resp = self.session.post(
                POST_URL,
                data={
                    "boletinBean.fecBolString": target_date.strftime("%d/%m/%Y"),
                    "boletinBean.tipoBol": "0",
                    "boton": "Buscar",
                },
                timeout=(10, 30),
                headers={"Referer": MENU_URL},
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("[BOC-CANT] POST failed: %s", exc)
            return []

        if not resp.text:
            logger.warning("[BOC-CANT] Empty response from boletines.do")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse(soup, target_date.isoformat())

    def _parse(self, soup: BeautifulSoup, pub_date: str) -> list[Act]:
        acts: list[Act] = []
        current_section = None
        current_section_name = ""
        current_organism = ""
        current_title = ""

        # Walk every element in document order, processing specific CSS classes
        for tag in soup.find_all(True):
            cls = set(tag.get("class") or [])
            text = tag.get_text(strip=True)
            upper = text.upper()

            # Section header: <span class="titulo2">N.Name</span>
            if "titulo2" in cls and tag.name == "span":
                m = re.match(r"^(\d+)\.", text)
                if m:
                    num = m.group(1)
                    if num == "1" or re.search(r"DISPOSICIONES\s+GENERALES", upper):
                        current_section = "I"
                    elif num == "3" or re.search(r"OTRAS\s+DISPOSICIONES", upper):
                        current_section = "III"
                    else:
                        current_section = None
                elif re.search(r"DISPOSICIONES\s+GENERALES", upper) and len(text) < 80:
                    current_section = "I"
                elif re.search(r"OTRAS\s+DISPOSICIONES", upper) and len(text) < 80:
                    current_section = "III"
                else:
                    current_section = None
                current_section_name = text.strip()
                current_organism = ""
                current_title = ""
                continue

            if current_section is None:
                continue

            # Organism: <span class="spanH4">Name</span>
            if "spanH4" in cls and tag.name == "span":
                current_organism = text
                current_title = ""
                continue

            # Title paragraph: <p>Text of the act</p> (not inside enlacesDoc)
            if tag.name == "p" and text and not tag.find(ANUNCIO_RE) and \
               not any(c in (tag.parent.get("class") or []) for c in ("enlacesDoc", "tipoPDFanuncio", "ancla")):
                # Only use as title if it has substantive content (not navigation links)
                if len(text) > 10 and not text.upper().startswith("SUBIR"):
                    current_title = text
                continue

            # Act link: only in <div class="tipoPDFanuncio"> to avoid duplicates
            if "tipoPDFanuncio" in cls and tag.name == "div":
                # Skip "Corrige a" cross-reference links (not primary acts)
                if tag.find("span", class_="negritaAnuncio"):
                    continue
                link = tag.find("a", href=ANUNCIO_RE)
                if not link:
                    link = tag.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
                if not link:
                    continue

                href = link["href"]
                if href.startswith("http"):
                    act_url = href
                else:
                    act_url = BASE_URL + "/boces/" + href.lstrip("/")

                m_id = ANUNCIO_RE.search(href)
                if m_id:
                    act_id = "BOC-CANT-" + m_id.group(1)
                else:
                    act_id = "BOC-CANT-" + href.split("/")[-1].replace(".pdf", "")

                # Use accumulated title; fall back to link text (PDF code)
                title = current_title or link.get_text(strip=True)

                acts.append(Act(
                    bulletin_id=self.bulletin_id,
                    act_id=act_id,
                    title=title,
                    section=current_section,
                    section_name=current_section_name,
                    rank="",
                    organism=current_organism,
                    pdf_url=act_url,
                    summary="",
                    pub_date=pub_date,
                ))
                # Reset title so consecutive acts under same organism get fresh titles
                current_title = ""

        logger.info("[BOC-CANT] Found %d acts in sections I/III", len(acts))
        return acts
