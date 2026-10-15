"""Polite downloading of annual report PDFs, with sha256 checksums kept in the repo.

`data/pdf_checksums.json` is committed. It records the URL, size and sha256 of every report
the first time it is downloaded, so a later download (on another machine, or after the file
was deleted) can prove it got exactly the same document.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.ingest.companies import Company

logger = logging.getLogger(__name__)

# BSE and NSE answer plain library User-Agents with 403, so send a normal browser one.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 120
CHUNK_SIZE = 1 << 16
RETRY_STATUSES = {429, 500, 502, 503, 504}


class Status(str, Enum):
    DOWNLOADED = "downloaded"
    SKIPPED = "already downloaded"
    NO_URL = "no report_url in companies.csv"
    MISMATCH = "checksum mismatch"
    FAILED = "failed"


@dataclass
class DownloadResult:
    company: Company
    status: Status
    path: Path | None = None
    sha256: str | None = None
    size: int | None = None
    message: str = ""


class DownloadError(Exception):
    """A download that failed after all retries, or returned something that isn't a PDF."""


def sha256_file(path: Path) -> str:
    """sha256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checksums(path: Path) -> dict[str, dict]:
    """Read data/pdf_checksums.json ({} if it doesn't exist yet)."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checksums(path: Path, checksums: dict[str, dict]) -> None:
    """Write the checksum file atomically, sorted so diffs stay small."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def fetch(
    url: str,
    dest: Path,
    session: requests.Session,
    max_retries: int = 3,
    sleep=time.sleep,
) -> None:
    """Stream `url` into `dest` (via a .part file), retrying network errors and 429/5xx.

    Raises DownloadError if every attempt fails or the response is not a PDF.
    """
    part = dest.with_name(dest.name + ".part")
    last_error = ""
    for attempt in range(max_retries + 1):
        if attempt:
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
            logger.warning("Retrying %s in %.1fs (attempt %d): %s", url, delay, attempt + 1, last_error)
            sleep(delay)
        try:
            with session.get(url, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) as resp:
                if resp.status_code in RETRY_STATUSES:
                    last_error = f"HTTP {resp.status_code}"
                    continue
                if resp.status_code != 200:
                    raise DownloadError(f"HTTP {resp.status_code} for {url}")
                with part.open("wb") as fh:
                    for chunk in resp.iter_content(CHUNK_SIZE):
                        fh.write(chunk)
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        with part.open("rb") as fh:
            head = fh.read(1024)
        if b"%PDF-" not in head:
            part.unlink(missing_ok=True)
            raise DownloadError(f"{url} did not return a PDF (starts with {head[:40]!r})")
        os.replace(part, dest)
        return

    part.unlink(missing_ok=True)
    raise DownloadError(f"Giving up on {url} after {max_retries + 1} attempts: {last_error}")


def download_all(
    companies: list[Company],
    pdf_dir: Path,
    checksum_file: Path,
    force: bool = False,
    pause_seconds: float = 3.0,
    session: requests.Session | None = None,
    sleep=time.sleep,
) -> list[DownloadResult]:
    """Download each company's report, skipping files that are already present and verified.

    - A file already on disk whose sha256 matches the record is skipped (no network call).
    - A file already on disk with no record yet gets recorded.
    - A fresh download whose sha256 differs from the record is kept as `<SYMBOL>.pdf.new` and
      reported as a mismatch; the record is never silently overwritten.
    - `pause_seconds` is waited between consecutive requests to the same host.
    """
    pdf_dir.mkdir(parents=True, exist_ok=True)
    checksums = load_checksums(checksum_file)
    session = session or requests.Session()
    session.headers.update(BROWSER_HEADERS)
    last_hit: dict[str, float] = {}
    results: list[DownloadResult] = []

    for company in companies:
        if not company.report_url:
            results.append(DownloadResult(company, Status.NO_URL))
            continue
        dest = pdf_dir / company.pdf_name
        record = checksums.get(company.nse_symbol)
        if record and record.get("url") != company.report_url:
            logger.warning("%s: report_url changed since the checksum was recorded", company.nse_symbol)

        if dest.exists() and not force:
            digest = sha256_file(dest)
            if record and record["sha256"] != digest:
                results.append(DownloadResult(
                    company, Status.MISMATCH, dest, digest, dest.stat().st_size,
                    f"file on disk does not match recorded sha256 {record['sha256'][:12]}...",
                ))
                continue
            if not record:
                checksums[company.nse_symbol] = _record(company, dest, digest)
                save_checksums(checksum_file, checksums)
            results.append(DownloadResult(company, Status.SKIPPED, dest, digest, dest.stat().st_size))
            continue

        host = urlparse(company.report_url).netloc
        wait = pause_seconds - (time.monotonic() - last_hit.get(host, -1e9))
        if wait > 0:
            sleep(wait)
        target = dest.with_name(dest.name + ".new") if record else dest
        logger.info("Downloading %s from %s", company.nse_symbol, host)
        try:
            fetch(company.report_url, target, session, sleep=sleep)
        except DownloadError as exc:
            results.append(DownloadResult(company, Status.FAILED, message=str(exc)))
            continue
        finally:
            last_hit[host] = time.monotonic()

        digest = sha256_file(target)
        size = target.stat().st_size
        if record:
            if record["sha256"] == digest:
                os.replace(target, dest)
                results.append(DownloadResult(company, Status.DOWNLOADED, dest, digest, size, "matches record"))
            else:
                results.append(DownloadResult(
                    company, Status.MISMATCH, target, digest, size,
                    f"server returned a different file than recorded ({record['sha256'][:12]}...); kept as {target.name}",
                ))
            continue
        checksums[company.nse_symbol] = _record(company, dest, digest)
        save_checksums(checksum_file, checksums)
        results.append(DownloadResult(company, Status.DOWNLOADED, dest, digest, size, "new checksum recorded"))

    return results


def _record(company: Company, path: Path, digest: str) -> dict:
    return {
        "url": company.report_url,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
