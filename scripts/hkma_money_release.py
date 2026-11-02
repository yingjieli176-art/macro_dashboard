"""Read adjusted HKD M2/M3 amounts from the original HKMA release annex.

The summary API can have null money fields after the press release is out.
Use the published amounts, never reconstruct a stock from rounded growth.
"""
import calendar
from datetime import datetime, timezone, timedelta
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import math
import re
from urllib.parse import urljoin, urlsplit

import requests

INDEX_URL = "https://www.hkma.gov.hk/eng/news-and-media/press-releases/"
PROVENANCE_FIELDS = ("money_source_url", "money_release_url", "money_source_sha256", "money_precision")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.current = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = [dict(attrs), []]

    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            attrs, text = self.current
            self.links.append((attrs.get("href", ""), attrs.get("title") or " ".join(text)))
            self.current = None


def _links(text):
    parser = _Links()
    parser.feed(text)
    return parser.links


def parse_release_text(text, period):
    """Accept only Table 1A's adjusted HKD amounts in HK$ million."""
    normalized = " ".join(text.split())
    reference = datetime.strptime(period, "%Y-%m")
    heading = rf"TABLE\s+1A\s*:\s*HONG\s+KONG\s+MONETARY\s+STATISTICS\s*[-–—]\s*{reference:%B}\s+{reference:%Y}\b"
    if (not re.search(heading, normalized, re.I)
            or not re.search(r"HK\$\s+Million", normalized, re.I)
            or not re.search(r"\badjusted to include foreign currency swap deposits\b", normalized, re.I)):
        raise ValueError("HKMA annex period, table, currency unit or adjusted concept mismatch")
    output = {"end_of_month": period}
    for aggregate in ("m2", "m3"):
        match = re.search(rf"\b{aggregate}\s*-\s*HK\$\s*(?:2\s+)?(\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?)\b", normalized, re.I)
        if match is None:
            raise ValueError(f"HKMA annex lacks adjusted HKD {aggregate.upper()} amount")
        value = float(match[1].replace(",", ""))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid HKMA money supply amount")
        output[aggregate + "_hkd"] = value
    if output["m3_hkd"] < output["m2_hkd"]:
        raise ValueError("HKMA M3 amount is smaller than M2")
    return output


def fetch_latest_money_release(*, get=None, now=None):
    from pypdf import PdfReader
    get = get or requests.get
    today = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=8))).date()

    def read(url):
        if urlsplit(url).hostname != "www.hkma.gov.hk" or urlsplit(url).scheme != "https":
            raise ValueError("Unexpected HKMA release host")
        response = get(url, headers={"User-Agent": "MacroDashboard/1.0"}, timeout=25)
        response.raise_for_status()
        return response

    candidates = []
    for href, title in _links(read(INDEX_URL).text):
        match = re.fullmatch(r"Monetary Statistics for ([A-Za-z]+) (\d{4})", title.strip())
        url = urljoin(INDEX_URL, href)
        if match is None or not re.search(r"/press-releases/\d{4}/\d{2}/\d{8}-\d+/$", url):
            continue
        reference = datetime.strptime(" ".join(match.groups()), "%B %Y")
        period_end = reference.date().replace(day=calendar.monthrange(reference.year, reference.month)[1])
        publication = datetime.strptime(url.rstrip("/").rsplit("/", 1)[-1].split("-")[0], "%Y%m%d").date()
        if period_end <= today and publication <= today:
            candidates.append((reference.strftime("%Y-%m"), url))
    if not candidates:
        raise ValueError("No published HKMA monthly monetary release found")
    period, release_url = max(candidates)
    annexes = [urljoin(release_url, href) for href, title in _links(read(release_url).text)
               if title.strip().lower() == "annex" and urlsplit(href).path.lower().endswith(".pdf")]
    if len(set(annexes)) != 1:
        raise ValueError("HKMA monetary release annex is missing or ambiguous")
    source_url = annexes[0]
    raw = read(source_url).content
    if not raw.startswith(b"%PDF-") or len(raw) > 10_000_000:
        raise ValueError("HKMA monetary annex is not a valid bounded PDF")
    reader = PdfReader(BytesIO(raw))
    row = parse_release_text(reader.pages[0].extract_text(), period)
    row.update(money_source_url=source_url, money_release_url=release_url,
               money_source_sha256=hashlib.sha256(raw).hexdigest(), money_precision="HK$ million, rounded as published")
    return row


def merge_release_pair(monthly, release):
    """Fill missing published months; preserve more precise API observations."""
    period = release["end_of_month"]
    row = monthly.setdefault(period, {"end_of_month": period})
    changed = False
    for field in ("m2_hkd", "m3_hkd"):
        if row.get(field) is None:
            row[field] = release[field]
            changed = True
    if changed:
        row.update({field: release[field] for field in PROVENANCE_FIELDS})
    return changed
