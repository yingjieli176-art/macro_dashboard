"""Collect explicit spot index observations from public Mysteel copper articles."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_platform.copper_tcrc import SNAPSHOT_PATH, validate_record

INDEX_URL = "https://news.mysteel.com/article/p-4536-------------1.html"
WEEKLY_INDEX_URL = "https://list1.mysteel.com/article/p-1948----020104---------1.html"


class PublicDocument(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.anchor, self.ignored = [], [], None, 0
        self.summary_depth = 0
        if isinstance(html, bytes):
            charset = re.search(br"charset=[\"']?([a-zA-Z0-9_-]+)", html[:4096])
            html = html.decode(charset[1].decode() if charset else "utf-8", errors="replace")
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'div' and (self.summary_depth or dict(attrs).get('id') == 'articleAiSummary'):
            self.summary_depth += 1
        if tag in ("script", "style"):
            self.ignored += 1
        if tag == "a":
            self.anchor = [dict(attrs).get("href", ""), []]

    def handle_endtag(self, tag):
        if tag == 'div' and self.summary_depth:
            self.summary_depth -= 1
        if tag in ("script", "style"):
            self.ignored = max(0, self.ignored - 1)
        if tag == "a" and self.anchor:
            self.links.append((self.anchor[0], "".join(self.anchor[1])))
            self.anchor = None

    def handle_data(self, data):
        if not self.ignored and not self.summary_depth:
            self.text.append(data)
            if self.anchor:
                self.anchor[1].append(data)


def parse_article(html, url, today=None):
    publication = re.search(r"/a/(\d{6})\d{2}/", url)
    if not publication:
        raise ValueError("Article publication date missing")
    published = datetime.strptime(publication[1], "%y%m%d").date()
    text = re.sub(r"\s+", "", "".join(PublicDocument(html).text)).replace("−", "-").replace("－", "-")
    # Only explicitly dated index fixings qualify. Bids, deals, annual
    # benchmarks, weekly changes and undated commentary cannot become points.
    pattern = (r"(\d{1,2})月(\d{1,2})日[，,\s]*"
               r"(?:Mysteel)?(?:进口)?(?:标准)?(?:干净)?铜精矿TC(?:/RC)?(?:周)?指数"
               r"(?:分别)?(?:为|报)[：:\s]*(-?\d+(?:\.\d+)?)\s*美元/干吨")
    rows = []
    for match in re.finditer(pattern, text, flags=re.I):
        month, day, tc = match.groups()
        year = published.year - int(int(month) == 12 and published.month == 1)
        observed = datetime(year, int(month), int(day)).date()
        if not 0 <= (published - observed).days <= 14:
            continue
        rows.append(validate_record(dict(observation_date=observed.isoformat(), tc_usd_dmt=float(tc),
            rc_cents_lb=round(float(tc) / 10, 6), source_url=url), today=today))
    # Weekly reports identify their fixing by an explicit title date range.
    # Do not assign the publication day to undated commentary or AI summaries.
    title = re.search(r'<title>(.*?)</title>', html.decode('utf-8', errors='replace') if isinstance(html, bytes) else html, re.S | re.I)
    week = re.search(r'Mysteel周报：铜精矿[^（(]*[（(](\d{1,2})\.(\d{1,2})[-—](\d{1,2})\.(\d{1,2})[）)]', title[1] if title else '')
    fixing = re.search(r'本周Mysteel标准干净铜精矿TC周指数为(-?\d+(?:\.\d+)?)美元/干吨', text)
    if week and fixing:
        sm, sd, em, ed = map(int, week.groups())
        end_year = published.year - int(em == 12 and published.month == 1)
        observed = datetime(end_year, em, ed).date()
        beginning = datetime(end_year - int(sm > em), sm, sd).date()
        if observed == published and observed.weekday() == 4 and 0 <= (observed - beginning).days <= 14:
            tc = float(fixing[1])
            rows.append(validate_record(dict(observation_date=observed.isoformat(), tc_usd_dmt=tc,
                rc_cents_lb=round(tc / 10, 6), source_url=url), today=today))
    return rows


def refresh(rows, path=SNAPSHOT_PATH, today=None):
    """Validate the complete candidate before atomically merging dated history."""
    if not rows:
        raise ValueError("No explicit public TC index fixings found; retaining last good snapshot")
    rows = [validate_record(row, today=today) for row in rows]
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    previous = {row["observation_date"]: validate_record(row, today=today) for row in payload["records"]}
    # An older export must not be described as a successful current refresh.
    if previous and max(r["observation_date"] for r in rows) < max(previous):
        raise ValueError("TC source returned older observations; retaining last good snapshot")
    for row in rows:
        previous[row["observation_date"]] = row
    payload["records"] = [previous[day] for day in sorted(previous)]
    payload["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    fd, temporary = tempfile.mkstemp(prefix=".copper-tcrc-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return payload


def collect():
    import requests
    session = requests.Session()
    links = set()
    for index_url in (WEEKLY_INDEX_URL, INDEX_URL):
        try:
            response = session.get(index_url, timeout=(10, 30))
            response.raise_for_status()
        except requests.RequestException:
            continue
        for href, title in PublicDocument(response.content).links:
            url = urljoin(index_url, href)
            if ("铜产业早读" in title or ("周报" in title and "铜精矿" in title)) and re.match(r"https://youse\.mysteel\.com/a/\d{8}/[A-Fa-f0-9]+\.html$", url):
                links.add(url)
    rows = []
    for url in sorted(links, reverse=True)[:16]:
        try:
            response = session.get(url, timeout=(10, 25))
            response.raise_for_status()
            rows.extend(parse_article(response.content, url))
        except (requests.RequestException, ValueError):
            continue
    return rows


def main():
    result = refresh(collect())
    print(json.dumps({"observations": len(result["records"]), "latest": result["records"][-1]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
