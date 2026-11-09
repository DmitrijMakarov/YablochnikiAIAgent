"""Bounded source extraction. Extracted text is untrusted data."""
import csv
import io
import ipaddress
import json
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zipfile import ZipFile

MAX_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 20_000
MAX_SNAPSHOT_BYTES = 20 * 1024 * 1024


def record(locator, text):
    return {"locator": locator, "text": text}


def table_rows(path):
    separator = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=separator, strict=True)
        start = 1
        for row in reader:
            end = reader.line_num
            locator = f"line:{start}" if end == start else f"line:{start}-{end}"
            yield locator, row
            start = end + 1


def extract(path):
    suffix = path.suffix.lower()
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("local file exceeds 10 MiB")
    if suffix in {".docx", ".xlsx"}:
        with ZipFile(path) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 40 * 1024 * 1024:
                raise ValueError("expanded Office file exceeds 40 MiB")
    if suffix in {".csv", ".tsv"}:
        for locator, row in table_rows(path):
            yield record(locator, json.dumps(row, ensure_ascii=False))
    elif suffix in {".txt", ".md"}:
        with path.open(encoding="utf-8-sig") as stream:
            for n, line in enumerate(stream, 1):
                if line.strip():
                    yield record(f"line:{n}", line.rstrip("\r\n"))
    elif suffix == ".pdf":
        from pypdf import PdfReader

        pdf = PdfReader(path)
        if pdf.is_encrypted:
            raise ValueError("encrypted PDF")
        for n, page in enumerate(pdf.pages, 1):
            value = page.extract_text() or ""
            if value.strip():
                yield record(f"page:{n}", value.strip())
    elif suffix == ".docx":
        from docx import Document

        doc = Document(path)
        for n, paragraph in enumerate(doc.paragraphs, 1):
            if paragraph.text.strip():
                yield record(f"paragraph:{n}", paragraph.text)
        for n, table in enumerate(doc.tables, 1):
            for row_n, row in enumerate(table.rows, 1):
                cells = [cell.text for cell in row.cells]
                if any(cells):
                    yield record(f"table:{n}/row:{row_n}", json.dumps(cells, ensure_ascii=False))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            for sheet in workbook.worksheets:
                for n, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    if len(row) > 500:
                        raise ValueError("worksheet exceeds 500 columns")
                    if any(value is not None for value in row):
                        yield record(f"sheet:{sheet.title}/row:{n}", json.dumps(
                            row, ensure_ascii=False, default=str))
        finally:
            workbook.close()
    else:
        raise ValueError(f"unsupported format {suffix}")


def snapshot_text(records):
    output = io.StringIO()
    seen = set()
    for n, item in enumerate(records, 1):
        locator = item["locator"]
        if not isinstance(locator, str) or not locator.strip() or locator in seen:
            raise ValueError("empty or duplicate locator")
        if not isinstance(item["text"], str) or not item["text"].strip():
            raise ValueError(f"empty text at {locator}")
        seen.add(locator)
        output.write(json.dumps(item, ensure_ascii=False) + "\n")
        if n > MAX_RECORDS or output.tell() > MAX_SNAPSHOT_BYTES:
            raise ValueError("extraction limit exceeded, split the input")
    result = output.getvalue()
    if not result:
        raise ValueError("no extractable text; for a scanned PDF use a reviewed OCR export")
    if len(result.encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("extraction limit exceeded, split the input")
    return result


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"} and self.hidden is None:
            self.hidden = tag
        if self.hidden is None and tag in {"br", "p", "li", "tr", "div", "section", "pre",
                                           "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == self.hidden:
            self.hidden = None
        elif self.hidden is None and tag in {"p", "li", "tr", "div", "section", "pre",
                                             "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.hidden is None:
            self.parts.append(data)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def public_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443}):
        raise ValueError("only explicit public HTTPS URLs on port 443 are allowed")
    return parsed.hostname


def fetch(url):
    host = public_url(url)
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError("host did not resolve exclusively to public addresses")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers={"User-Agent": "ProductStrategyResearch/0.1"}),
                     timeout=10) as response:
        mime = response.headers.get_content_type()
        if mime not in {"text/plain", "text/html"}:
            raise ValueError(f"unsupported web content type {mime}")
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("web response exceeds 2 MiB")
        value = data.decode(response.headers.get_content_charset() or "utf-8", errors="strict")
    if mime == "text/html":
        page = PageText()
        page.feed(value)
        page.close()
        value = "".join(page.parts)
    return (record(f"web:line:{n}", line.strip())
            for n, line in enumerate(value.splitlines(), 1) if line.strip())


def read_records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
