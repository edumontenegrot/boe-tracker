"""BOE estatal — API JSON oficial.

Endpoint: https://www.boe.es/datosabiertos/api/boe/sumario/{YYYYMMDD}
Documentación: https://www.boe.es/datosabiertos/
"""

import logging
from datetime import date
from typing import Optional

from .base import Act, BaseScraper, INCLUDED_SECTIONS

logger = logging.getLogger(__name__)

API_URL = "https://www.boe.es/datosabiertos/api/boe/sumario/{date}"
PDF_BASE = "https://www.boe.es"

SECTION_NAMES = {
    "1": "Disposiciones generales",
    "2": "Autoridades y personal",
    "3": "Otras disposiciones",
    "4": "Administración de Justicia",
    "5": "Anuncios",
    "T": "Tribunal Constitucional",
}

# Mapping BOE section number → canonical roman numeral used project-wide
SECTION_MAP = {
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "T": "TC",
}


class BOEScraper(BaseScraper):
    bulletin_id = "BOE"
    bulletin_name = "Boletín Oficial del Estado"
    base_url = "https://www.boe.es"

    def fetch(self, target_date: Optional[date] = None) -> list[Act]:
        target_date = target_date or date.today()
        date_str = target_date.strftime("%Y%m%d")
        url = API_URL.format(date=date_str)

        logger.info("[BOE] Fetching sumario for %s", target_date.isoformat())
        resp = self._safe_get(url, headers={"Accept": "application/json"})
        if resp is None:
            return []

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error("[BOE] Invalid JSON response: %s", exc)
            return []

        return self._parse(data, target_date.isoformat())

    def _parse(self, data: dict, pub_date: str) -> list[Act]:
        acts: list[Act] = []

        try:
            diario = data["data"]["sumario"]["diario"]
        except (KeyError, TypeError):
            logger.error("[BOE] Unexpected response structure")
            return acts

        # diario may contain a single section dict or a list
        secciones = diario.get("seccion", [])
        if isinstance(secciones, dict):
            secciones = [secciones]

        for seccion in secciones:
            num = str(seccion.get("@num", seccion.get("num", "")))
            roman = SECTION_MAP.get(num, num)
            if roman not in INCLUDED_SECTIONS:
                continue

            section_name = SECTION_NAMES.get(num, seccion.get("@nombre", ""))
            departamentos = seccion.get("departamento", [])
            if isinstance(departamentos, dict):
                departamentos = [departamentos]

            for dept in departamentos:
                organism = dept.get("nombre", "")
                epigrafes = dept.get("epigrafe", [])
                if isinstance(epigrafes, dict):
                    epigrafes = [epigrafes]

                for epigrafe in epigrafes:
                    rank = epigrafe.get("nombre", "")
                    items = epigrafe.get("item", [])
                    if isinstance(items, dict):
                        items = [items]

                    for item in items:
                        act_id = item.get("identificador", "")
                        title = item.get("titulo", "")
                        summary = item.get("texto", "")
                        pdf_path = item.get("url_pdf", {})
                        if isinstance(pdf_path, dict):
                            pdf_path = pdf_path.get("#text", "")
                        pdf_url = (PDF_BASE + pdf_path) if pdf_path else ""

                        acts.append(Act(
                            bulletin_id=self.bulletin_id,
                            act_id=act_id,
                            title=title,
                            section=roman,
                            section_name=section_name,
                            rank=rank,
                            organism=organism,
                            pdf_url=pdf_url,
                            summary=summary,
                            pub_date=pub_date,
                        ))

        logger.info("[BOE] Found %d acts in sections I/III", len(acts))
        return acts
