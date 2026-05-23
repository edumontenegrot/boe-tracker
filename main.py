#!/usr/bin/env python3
"""BOE Tracker — daily download and upload pipeline.

Usage:
    python main.py                     # today
    python main.py --date 2026-05-23   # specific date
    python main.py --bulletins BOE BOCM  # only selected bulletins
    python main.py --no-upload         # skip Google Drive upload (dry-run)
"""

import argparse
import logging
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from scrapers import ALL_SCRAPERS
from utils.drive_uploader import DriveUploader
from utils.pdf_downloader import PDFDownloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def latest_weekday(d: date) -> date:
    """Return d itself if it's Mon–Fri, otherwise roll back to the previous Friday."""
    # weekday(): Monday=0 … Sunday=6
    if d.weekday() < 5:
        return d
    days_back = d.weekday() - 4  # Saturday → 1, Sunday → 2
    return d - timedelta(days=days_back)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily BOE/CCAA downloader")
    parser.add_argument(
        "--date",
        default=None,
        help="Publication date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--bulletins",
        nargs="*",
        default=None,
        help="Bulletin IDs to process (e.g. BOE BOCM DOGC). Default: all.",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading to Google Drive (dry-run mode)",
    )
    return parser.parse_args()


def run(target_date: date, bulletin_filter: list[str] | None, upload: bool) -> dict:
    """Main pipeline. Returns a summary dict keyed by bulletin_id."""
    summary: dict[str, dict] = {}

    # Initialise uploader once (fails fast if credentials are missing)
    uploader = None
    if upload:
        try:
            uploader = DriveUploader()
        except EnvironmentError as exc:
            logger.error("Cannot initialise Drive uploader: %s", exc)
            logger.warning("Continuing without uploading (pass --no-upload to suppress this)")
            uploader = None

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

        # 2. Download PDFs into a temp directory
        with tempfile.TemporaryDirectory(prefix=f"boe-{bid}-") as tmp_dir:
            pdf_dir = Path(tmp_dir) / "pdfs"
            downloader = PDFDownloader(pdf_dir)

            pdf_items = [
                (a.pdf_url, _safe_filename(a.act_id) + ".pdf")
                for a in acts
                if a.pdf_url
            ]
            pdf_results = downloader.download_batch(pdf_items)

            for fname, local_path in pdf_results.items():
                if local_path is not None:
                    stats["pdfs_ok"] += 1
                else:
                    stats["pdfs_failed"] += 1

            # 3. Upload to Drive
            if uploader is not None:
                pub_date = target_date.isoformat()
                try:
                    uploader.upload_sumario(bid, pub_date, acts_dicts)
                except Exception as exc:
                    logger.error("[%s] Failed to upload sumario: %s", bid, exc)
                    stats["errors"].append(f"sumario upload: {exc}")

                for fname, local_path in pdf_results.items():
                    if local_path is None:
                        continue
                    try:
                        uploader.upload_pdf(bid, pub_date, local_path)
                    except Exception as exc:
                        logger.error("[%s] Failed to upload %s: %s", bid, fname, exc)
                        stats["errors"].append(f"pdf upload {fname}: {exc}")

        summary[bid] = stats

    return summary


def print_summary(summary: dict, target_date: date):
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY for %s", target_date.isoformat())
    logger.info("=" * 60)
    total_acts = 0
    total_pdfs = 0
    for bid, stats in summary.items():
        acts = stats["acts"]
        pdfs_ok = stats["pdfs_ok"]
        pdfs_fail = stats["pdfs_failed"]
        errors = stats["errors"]
        total_acts += acts
        total_pdfs += pdfs_ok
        status = "OK" if not errors else f"WARN ({len(errors)} errors)"
        logger.info(
            "  %-12s  acts: %3d  pdfs: %3d downloaded  %3d failed  [%s]",
            bid, acts, pdfs_ok, pdfs_fail, status,
        )
        for err in errors:
            logger.info("             └─ %s", err)
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
            logger.error("Invalid date format: %s (expected YYYY-MM-DD)", args.date)
            sys.exit(1)
    else:
        target_date = date.today()

    adjusted = latest_weekday(target_date)
    if adjusted != target_date:
        logger.info(
            "%s is a weekend — using most recent weekday: %s",
            target_date.isoformat(),
            adjusted.isoformat(),
        )
        target_date = adjusted

    logger.info("BOE Tracker — date: %s", target_date.isoformat())

    upload = not args.no_upload
    if not upload:
        logger.info("Dry-run mode: Google Drive upload disabled")

    summary = run(target_date, args.bulletins, upload)
    print_summary(summary, target_date)

    # Exit with non-zero code only if ALL bulletins had errors
    all_failed = all(bool(s["errors"]) and s["acts"] == 0 for s in summary.values())
    sys.exit(1 if all_failed else 0)


if __name__ == "__main__":
    main()
