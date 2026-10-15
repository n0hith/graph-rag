"""Tests for PDF downloading and checksum records, with a fake HTTP session (no network)."""

import hashlib
import json

import pytest

from src.ingest.companies import Company, select_companies
from src.ingest.download import BROWSER_HEADERS, Status, download_all

PDF_A = b"%PDF-1.7\n" + b"a" * 5000
PDF_B = b"%PDF-1.7\n" + b"b" * 5000


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status_code = status
        self.body = body

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i : i + size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    """Returns queued responses per URL and records each request."""

    def __init__(self, responses: dict[str, list[FakeResponse]]) -> None:
        self.responses = {url: list(r) for url, r in responses.items()}
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []

    def get(self, url, stream, timeout):
        self.calls.append(url)
        return self.responses[url].pop(0)


URL = "https://example.invalid/tcs.pdf"
COMPANY = Company("Tata Consultancy Services Limited", "TCS", "L22210MH1995PLC084781", URL)


def _run(tmp_path, session, **kwargs):
    return download_all(
        [COMPANY], tmp_path / "pdfs", tmp_path / "checksums.json",
        session=session, sleep=lambda s: None, **kwargs,
    )


def test_downloads_and_records_checksum(tmp_path):
    session = FakeSession({URL: [FakeResponse(200, PDF_A)]})
    [result] = _run(tmp_path, session)
    assert result.status is Status.DOWNLOADED
    assert (tmp_path / "pdfs" / "TCS.pdf").read_bytes() == PDF_A
    record = json.loads((tmp_path / "checksums.json").read_text())["TCS"]
    assert record["sha256"] == hashlib.sha256(PDF_A).hexdigest()
    assert record["url"] == URL and record["bytes"] == len(PDF_A)
    assert session.headers["User-Agent"] == BROWSER_HEADERS["User-Agent"]


def test_second_run_skips_without_network(tmp_path):
    _run(tmp_path, FakeSession({URL: [FakeResponse(200, PDF_A)]}))
    session = FakeSession({URL: []})
    [result] = _run(tmp_path, session)
    assert result.status is Status.SKIPPED
    assert session.calls == []


def test_retries_server_errors_then_succeeds(tmp_path):
    session = FakeSession({URL: [FakeResponse(503), FakeResponse(429), FakeResponse(200, PDF_A)]})
    [result] = _run(tmp_path, session)
    assert result.status is Status.DOWNLOADED
    assert len(session.calls) == 3


def test_403_is_not_retried(tmp_path):
    session = FakeSession({URL: [FakeResponse(403)]})
    [result] = _run(tmp_path, session)
    assert result.status is Status.FAILED
    assert "403" in result.message
    assert len(session.calls) == 1


def test_non_pdf_response_fails_and_leaves_no_file(tmp_path):
    session = FakeSession({URL: [FakeResponse(200, b"<html>blocked</html>")]})
    [result] = _run(tmp_path, session)
    assert result.status is Status.FAILED
    assert not list((tmp_path / "pdfs").iterdir())


def test_changed_file_on_server_is_flagged_not_overwritten(tmp_path):
    _run(tmp_path, FakeSession({URL: [FakeResponse(200, PDF_A)]}))
    [result] = _run(tmp_path, FakeSession({URL: [FakeResponse(200, PDF_B)]}), force=True)
    assert result.status is Status.MISMATCH
    assert (tmp_path / "pdfs" / "TCS.pdf").read_bytes() == PDF_A
    assert (tmp_path / "pdfs" / "TCS.pdf.new").read_bytes() == PDF_B
    record = json.loads((tmp_path / "checksums.json").read_text())["TCS"]
    assert record["sha256"] == hashlib.sha256(PDF_A).hexdigest()


def test_edited_file_on_disk_is_flagged(tmp_path):
    _run(tmp_path, FakeSession({URL: [FakeResponse(200, PDF_A)]}))
    (tmp_path / "pdfs" / "TCS.pdf").write_bytes(PDF_B)
    [result] = _run(tmp_path, FakeSession({URL: []}))
    assert result.status is Status.MISMATCH


def test_missing_url_is_reported(tmp_path):
    company = Company("X Limited", "X", "", "")
    [result] = download_all([company], tmp_path / "pdfs", tmp_path / "c.json", session=FakeSession({}))
    assert result.status is Status.NO_URL


def test_select_companies_by_symbol():
    other = Company("Infosys Limited", "INFY", "", "")
    assert select_companies([COMPANY, other], ["infy"]) == [other]
    assert select_companies([COMPANY, other], None) == [COMPANY, other]
    with pytest.raises(ValueError, match="NOPE"):
        select_companies([COMPANY, other], ["NOPE"])
