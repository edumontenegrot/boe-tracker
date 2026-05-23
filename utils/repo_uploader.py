"""RepoUploader — saves sumarios and PDFs to a local output/ directory.

The GitHub Actions workflow then commits and pushes output/ to the 'data' branch.

Structure:
  output/
    {YYYY}/
      {MM}/
        {DD}/
          {BULLETIN_ID}/
            sumario.json
            pdfs/
              {act_id}.pdf
            texts/
              {act_id}.txt
              {act_id}.json
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("output")


class RepoUploader:
    def __init__(self, root: Path = OUTPUT_ROOT):
        self.root = root

    def _bulletin_dir(self, bulletin_id: str, pub_date: str) -> Path:
        year, month, day = pub_date.split("-")
        return self.root / year / month / day / bulletin_id

    def _pdf_dir(self, bulletin_id: str, pub_date: str) -> Path:
        return self._bulletin_dir(bulletin_id, pub_date) / "pdfs"

    def _text_dir(self, bulletin_id: str, pub_date: str) -> Path:
        return self._bulletin_dir(bulletin_id, pub_date) / "texts"

    def upload_sumario(
        self, bulletin_id: str, pub_date: str, acts: list[dict]
    ) -> Optional[Path]:
        """Write sumario.json. Returns the path written."""
        dest_dir = self._bulletin_dir(bulletin_id, pub_date)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "sumario.json"
        content = json.dumps(
            {"bulletin": bulletin_id, "date": pub_date, "acts": acts},
            ensure_ascii=False,
            indent=2,
        )
        dest.write_text(content, encoding="utf-8")
        logger.info("Saved sumario: %s", dest)
        return dest

    def upload_pdf(
        self, bulletin_id: str, pub_date: str, local_path: Path
    ) -> Optional[Path]:
        """Copy a downloaded PDF into the output tree. Returns dest path."""
        dest_dir = self._pdf_dir(bulletin_id, pub_date)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / local_path.name
        shutil.copy2(local_path, dest)
        logger.debug("Saved PDF: %s", dest)
        return dest

    def upload_act_text(
        self, bulletin_id: str, pub_date: str, act_id: str, text: str
    ) -> Path:
        """Write extracted plain text for one act. Returns dest path."""
        dest_dir = self._text_dir(bulletin_id, pub_date)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{act_id}.txt"
        dest.write_text(text, encoding="utf-8")
        logger.debug("Saved text: %s", dest)
        return dest

    def upload_act_json(
        self, bulletin_id: str, pub_date: str, act_data: dict
    ) -> Path:
        """Write structured act JSON (metadata + extracted text). Returns dest path."""
        dest_dir = self._text_dir(bulletin_id, pub_date)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{act_data['act_id']}.json"
        dest.write_text(
            json.dumps(act_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("Saved act JSON: %s", dest)
        return dest
