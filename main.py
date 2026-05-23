#!/usr/bin/env python3
"""BOE Tracker — daily download pipeline.

Downloads sumarios and PDFs from BOE + 17 CCAA official bulletins and saves
them to output/ (which the CI workflow then commits to the 'data' branch).

Usage:
    python main.py                       # today (auto-adjusts weekends → Friday)
    python main.py --date 2026-05-22     # specific date
    python main.py --bulletins BOE DOGC  # only selected bulletins
    python main.py --output /tmp/boe     # custom output directory
"""

import argparse
import logging
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from scrapers import ALL_SCRAPERS
from utils.repo_uploader import RepoUploader
from utils.pdf_downloader import PDFDownloader
from utils.pdf_extractor import extract_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def latest_weekday(d: date) -> date:
    """Return d itself if Mon–Fri, otherwise roll back to the previous Friday."""
    if d.weekday() < 5:
        return d
    days_back = d.weekday() - 4  # Saturday→1, Sunday→2
    return d - timedelta(days=days_back)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily BOE/CCAA downloader")
    parser.add_argument("--date", default=None,
                        help="Publication date YYYY-MM-DD (default: today)")
    parser.add_argument("--bulletins", nargs="*", default=None,
                        help="Bulletin IDs to process. Default: all.")
    parser.add_argument("--output", default="output",
                        help="Output directory (default: output/)")
    return parser.parse_args()


def run(target_date: date, bulletin_filter: list[str] | None, output_dir: Path) -> dict:
    """Main pipeline. Returns a summary dict keyed by bulletin_id."""
    summary: dict[str, dict] = {}
    uploader = RepoUploader(root=output_dir)

    scrapers = [
        cls() for cls in ALL_SCRAPERS
        if bulletin_filter is None or cls.bulletin_id in bulletin_filter
    ]

    for scraper in scrapers:
        bid = scraper.bulletin_id
        logger.info("=" * 60)
        logger.info("Processing: %s — %s", bid, scraper.bulletin_name)
        stats = {"acts": 0, "pdfs_ok": 0, "pdfs_failed": 0, "errors": []}

        # 1. Fetch acts
        try:
            acts = scraper.fetch(target_date)
        except Exception as exc:
            logger.error("[%s] Scraper error: %s", bid, exc, exc_info=True)
            stats["errors"].append(str(exc))
            summary[bid] = stats
            continue

        stats["acts"] = len(acts)
        if not acts:
            logger.info("[%s] No acts found — bulletin may not publish today", bid)
            summary[bid] = stats
            continue

        acts_dicts = [a.to_dict() for a in acts]

        # 2. Save sumario.json
        try:
            uploader.upload_sumario(bid, target_date.isoformat(), acts_dicts)
        except Exception as exc:
            logger.error("[%s] Failed to save sumario: %s", bid, exc)
            stats["errors"].append(f"sumario: {exc}")

        # 3. Download PDFs into a temp dir, then move to output/
        with tempfile.TemporaryDirectory(prefix=f"boe-{bid}-") as tmp_dir:
            pdf_tmp = Path(tmp_dir) / "pdfs"
            downloader = PDFDownloader(pdf_tmp)

            pdf_items = [
                (a.pdf_url, _safe_filename(a.act_id) + ".pdf")
                for a in acts if a.pdf_url
            ]
            act_by_fname = {_safe_filename(a.act_id) + ".pdf": a for a in acts if a.pdf_url}
            pdf_results = downloader.download_batch(pdf_items)

            for fname, local_path in pdf_results.items():
                if local_path is not None:
                    try:
                        uploader.upload_pdf(bid, target_date.isoformat(), local_path)
                        stats["pdfs_ok"] += 1
                    except Exception as exc:
                        logger.error("[%s] Failed to save %s: %s", bid, fname, exc)
                        stats["pdfs_failed"] += 1
                        stats["errors"].append(f"pdf {fname}: {exc}")
                        continue

                    # 4. Extract text and save .txt + .json alongside the PDF
                    act = act_by_fname.get(fname)
                    if act:
                        extracted = extract_pdf(local_path)
                        uploader.upload_act_text(
                            bid, target_date.isoformat(), act.act_id, extracted["text"]
                        )
                        uploader.upload_act_json(
                            bid, target_date.isoformat(), {
                                "act_id":       act.act_id,
                                "bulletin_id":  act.bulletin_id,
                                "pub_date":     act.date,
                                "title":        act.title,
                                "section":      act.section,
                                "section_name": act.section_name,
                                "organism":     act.organism,
                                "pdf_url":      act.pdf_url,
                                "pages":        extracted["pages"],
                                "text":         extracted["text"],
                            }
                        )
                else:
                    stats["pdfs_failed"] += 1

        summary[bid] = stats

    return summary


def print_summary(summary: dict, target_date: date):
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY for %s", target_date.isoformat())
    logger.info("=" * 60)
    total_acts = total_pdfs = 0
    for bid, stats in summary.items():
        acts = stats["acts"]
        pdfs_ok = stats["pdfs_ok"]
        pdfs_fail = stats["pdfs_failed"]
        errors = stats["errors"]
        total_acts += acts
        total_pdfs += pdfs_ok
        status = "OK" if not errors else f"WARN ({len(errors)} errors)"
        logger.info("  %-12s  acts: %3d  pdfs: %3d downloaded  %3d failed  [%s]",
                    bid, acts, pdfs_ok, pdfs_fail, status)
    logger.info("-" * 60)
    logger.info("  TOTAL         acts: %3d  pdfs: %3d downloaded", total_acts, total_pdfs)
    logger.info("=" * 60)


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def main():
    args = parse_args()

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid date: %s (expected YYYY-MM-DD)", args.date)
            sys.exit(1)
    else:
        target_date = date.today()

    adjusted = latest_weekday(target_date)
    if adjusted != target_date:
        logger.info("%s is a weekend — using most recent weekday: %s",
                    target_date.isoformat(), adjusted.isoformat())
        target_date = adjusted

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("BOE Tracker — date: %s  output: %s", target_date.isoformat(), output_dir)

    summary = run(target_date, args.bulletins, output_dir)
    print_summary(summary, target_date)

    all_failed = all(bool(s["errors"]) and s["acts"] == 0 for s in summary.values())
    sys.exit(1 if all_failed else 0)


if __name__ == "__main__":
    main()
