#!/usr/bin/env python3
"""Fetch the Modern Sailing schedule widget and write a clean events.json.

The club's /schedule page embeds a Mindbody "Healcode" enrollments widget. The
widget is served as a small JavaScript file that assigns an HTML table to a div,
so there is no JSON API: we download that file, decode the embedded HTML string
and parse the table rows.

Row types in the table:
  * regular rows   - tr[data-hc-id], one course/sail/clinic each
  * summary rows   - tr.healcode-summary-course, a race "series" header with the
                     series name and a sign-up link but no dates
  * child rows     - tr.child, the individual race sessions that belong to the
                     closest preceding summary row (they inherit its name/link)

Standard library only. Usage:
    python scripts/scrape.py --out site/events.json
    python scripts/scrape.py --input saved_widget.js --out /tmp/events.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

WIDGET_URL = "https://widgets.mindbodyonline.com/widgets/enrollments/db8098683b"
DESCRIPTION_URL = ("https://widgets.mindbodyonline.com/widgets/class_lists/078098a3a2/"
                   "class_description?site_mbo_id=21775&class_description_id={id}&widget_type=Enrollment")
DESCRIPTION_TTL_DAYS = 7      # descriptions rarely change; re-fetch weekly
DESCRIPTION_MAX_FETCHES = 60  # hard cap per run
DESCRIPTION_DELAY_S = 0.5     # pause between description requests
ALLOWED_FETCH_HOSTS = {"widgets.mindbodyonline.com"}
SCHEDULE_URL = "https://www.modernsailing.com/schedule"
USER_AGENT = (
    "modern-sailing-schedule/1.0 (personal club-member project; "
    "fetches one public page a few times a day)"
)
MIN_EVENTS = 20          # refuse to publish if the parse looks broken
MAX_SKIPPED_RATIO = 0.10  # refuse to publish if too many rows fail to parse

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
DAY_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


class ScrapeError(Exception):
    pass


# --------------------------------------------------------------------------- fetch

def fetch(url: str, attempts: int = 3) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_FETCH_HOSTS:
        raise ScrapeError(f"refusing to fetch {url!r}")
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:  # network errors are retried, then raised
            last = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise ScrapeError(f"could not fetch widget after {attempts} attempts: {last}")


# ------------------------------------------------------------------ JS -> HTML

_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def extract_html(js: str) -> str:
    """Decode the single-quoted JS string passed to `.html('...')`."""
    marker = ".html('"
    start = js.find(marker)
    if start < 0:
        raise ScrapeError("widget response has no .html('...') payload; format changed?")
    i = start + len(marker)
    out: list[str] = []
    n = len(js)
    while i < n:
        c = js[i]
        if c == "\\":
            i += 1
            if i >= n:
                break
            e = js[i]
            if e == "u":
                out.append(chr(int(js[i + 1:i + 5], 16)))
                i += 5
            elif e == "x":
                out.append(chr(int(js[i + 1:i + 3], 16)))
                i += 3
            else:
                out.append(_SIMPLE_ESCAPES.get(e, e))
                i += 1
            continue
        if c == "'":
            text = "".join(out)
            # re-join UTF-16 surrogate pairs produced by 😀-style escapes
            return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
        out.append(c)
        i += 1
    raise ScrapeError("unterminated string in widget response")


# ----------------------------------------------------------------- HTML parsing

class _RowParser(HTMLParser):
    """Collect every <tr> that has at least one <td> as a list of cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._row: dict | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "tr":
            self._row = {"attrs": a, "classes": a.get("class", "").split(), "cells": []}
        elif self._row is None:
            return
        elif tag == "td":
            self._cell = {"classes": a.get("class", "").split(), "text": [], "hrefs": [],
                          "data_urls": [], "ids": []}
        elif self._cell is not None:
            if a.get("id"):
                self._cell["ids"].append(a["id"])
            if tag == "a":
                if a.get("href"):
                    self._cell["hrefs"].append(a["href"])
                if a.get("data-url"):
                    self._cell["data_urls"].append(a["data-url"])

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._cell["text"] = _clean("".join(self._cell["text"]))
            self._row["cells"].append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row["cells"]:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_rows(html_text: str) -> list[dict]:
    p = _RowParser()
    p.feed(html_text)
    p.close()
    return p.rows


# --------------------------------------------------------------- row -> event

_DATE_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.I)


def _iso(m: tuple[str, str, str]) -> str:
    mon, day, year = m
    return f"{int(year):04d}-{MONTHS[mon]:02d}-{int(day):02d}"


def _to_24h(h: str, mi: str, ap: str) -> tuple[int, int]:
    hour = int(h) % 12 + (12 if ap.upper() == "PM" else 0)
    return hour, int(mi)


def categorize(title: str) -> str:
    t = title.lower()
    if "checkout" in t:
        return "Checkouts"
    if t.startswith(("regatta", "training")):
        return "Racing"
    if "info session" in t:
        return "Talks & Info"
    if "flotilla" in t:
        return "Trips"
    if t.startswith("club sail"):
        return "Club Sails"
    if t.startswith("development sail"):
        return "Development Sails"
    if "orientation sail" in t or "introductory sail" in t:
        return "Intro & Orientation"
    if "clinic" in t:
        return "Clinics"
    if "asa" in t:
        return "ASA Courses"
    return "Other"


def start_bucket(hour: int) -> str:
    if hour < 12:
        return "morning"
    if hour < 16:
        return "afternoon"
    return "evening"


def day_kind(days: list[int]) -> str:
    if not days:
        return "mixed"
    if all(d < 5 for d in days):
        return "week"
    if all(d >= 5 for d in days):
        return "weekend"
    return "mixed"


def _cell(row: dict, cls: str) -> dict | None:
    for c in row["cells"]:
        if cls in c["classes"]:
            return c
    return None


def _https_or_empty(url: str) -> str:
    return url if url.startswith("https://") else ""


def build_event(row: dict, series: dict | None) -> dict:
    """Turn a regular or child row into an event dict. Raises ValueError on bad data."""
    date_cell, time_cell = _cell(row, "healcode-date-field"), _cell(row, "healcode-time-field")
    days_cell, btn_cell = _cell(row, "healcode-days-field"), _cell(row, "healcode-button-field")
    cls_cell, boat_cell, loc_cell = _cell(row, "mbo_class"), _cell(row, "trainer"), _cell(row, "location")
    if not (date_cell and time_cell and cls_cell and loc_cell):
        raise ValueError("missing expected columns")

    dates = _DATE_RE.findall(date_cell["text"])
    if not dates:
        raise ValueError(f"no date in {date_cell['text']!r}")
    start, end = _iso(dates[0]), _iso(dates[-1])

    times = _TIME_RE.findall(time_cell["text"])
    if not times:
        raise ValueError(f"no time in {time_cell['text']!r}")
    sh, sm = _to_24h(*times[0])
    label = " – ".join(f"{int(h)}:{m} {ap.upper()}" for h, m, ap in times[:2])

    days = sorted({DAY_INDEX[d] for d in re.findall(r"Mon|Tue|Wed|Thu|Fri|Sat|Sun",
                                                    days_cell["text"] if days_cell else "")})
    title = cls_cell["text"]

    item_id = ""
    for sid in cls_cell["ids"]:
        m = re.match(r"item_(\d+)_mbo_class$", sid)
        if m:
            item_id = m.group(1)
    details_url = next((u for u in cls_cell["data_urls"] if "class_description" in u), "")
    desc_match = re.search(r"class_description_id=(\d+)", details_url)
    description_id = desc_match.group(1) if desc_match else ""

    signup = next((h for h in (btn_cell["hrefs"] if btn_cell else []) if h.startswith("https://")), "")
    series_name = series["name"] if series else ""
    if not signup and series:
        signup = series["signup_url"]

    return {
        # tr ids change on every widget request, so build a stable id instead
        "id": f"{item_id or 'x'}-{start}-{sh:02d}{sm:02d}",
        "title": title,
        "category": categorize(title),
        "start": start,
        "end": end,
        "days": days,
        "day_kind": day_kind(days),
        "time_label": label,
        "start_time": f"{sh:02d}:{sm:02d}",
        "start_bucket": start_bucket(sh),
        "boat": boat_cell["text"] if boat_cell else "",
        "location": loc_cell["text"],
        "signup_url": _https_or_empty(signup),
        "available": bool(signup),
        "underway": "healcode-underway" in row["classes"],
        "series": series_name,
        "details_url": _https_or_empty(details_url),
        "description_id": description_id,
    }


def build_events(rows: list[dict]) -> tuple[list[dict], int]:
    events: list[dict] = []
    skipped = 0
    series: dict | None = None
    for row in rows:
        classes = row["classes"]
        if "healcode-summary-course" in classes:
            cells = row["cells"]
            btn = next((c for c in cells if "healcode-button-field" in c["classes"]), None)
            name = cells[4]["text"] if len(cells) > 4 else ""
            series = {"name": name,
                      "signup_url": next((h for h in (btn["hrefs"] if btn else [])
                                          if h.startswith("https://")), "")}
            continue
        is_child = "child" in classes
        if not is_child and "data-hc-id" not in row["attrs"]:
            continue
        if not is_child:
            series = None  # a regular row ends any series block
        try:
            events.append(build_event(row, series if is_child else None))
        except (ValueError, KeyError) as exc:
            skipped += 1
            print(f"warning: skipped row {row['attrs'].get('id', '?')}: {exc}", file=sys.stderr)

    # de-duplicate ids defensively (same class id + same start + same time)
    seen: dict[str, int] = {}
    for e in events:
        n = seen.get(e["id"], 0)
        seen[e["id"]] = n + 1
        if n:
            e["id"] = f"{e['id']}-{n + 1}"
    events.sort(key=lambda e: (e["start"], e["start_time"], e["title"], e["location"]))
    return events, skipped


# ---------------------------------------------------------------- descriptions

class _DescParser(HTMLParser):
    """Extract paragraphs of plain text from the page's div.class_description.

    Two layouts exist: one <div> per paragraph with <br> line breaks inside, and
    a <div> holding bare text followed by <p> tags. Both flush on div/p/br
    boundaries. Markup (links, bold) is dropped on purpose: we only keep text.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip = 0
        self.lines: list[str] = []
        self._buf: list[str] = []

    def _flush(self) -> None:
        text = _clean("".join(self._buf))
        if text:
            self.lines.append(text)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.depth == 0:
            classes = dict(attrs).get("class") or ""
            if tag == "div" and "class_description" in classes.split():
                self.depth = 1
            return
        if tag == "div":
            self.depth += 1
            self._flush()
        elif tag in ("br", "p"):
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if self.depth == 0:
            return
        if tag == "div":
            self._flush()
            self.depth -= 1
        elif tag == "p":
            self._flush()

    def handle_data(self, data):
        if self.depth and not self.skip:
            self._buf.append(data)


def parse_description(html_text: str) -> list[str]:
    p = _DescParser()
    p.feed(html_text)
    p.close()
    p._flush()
    return p.lines


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def load_cache(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}  # a corrupt cache just means we re-fetch


def save_cache(path: str | None, cache: dict) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


def collect_descriptions(ids, cache: dict, fetcher, now: datetime, *,
                         ttl_days: int = DESCRIPTION_TTL_DAYS,
                         max_fetches: int = DESCRIPTION_MAX_FETCHES,
                         delay: float = DESCRIPTION_DELAY_S,
                         sleep=time.sleep) -> tuple[dict[str, list[str]], int]:
    """Return {description_id: [paragraphs]}; fetch only missing or stale ids.

    `cache` is updated in place. A failed fetch never aborts the run: a stale
    cached copy is used if there is one, otherwise that class has no description.
    """
    result: dict[str, list[str]] = {}
    fetched = 0
    for did in sorted({i for i in ids if i.isdigit()}, key=int):
        entry = cache.get(did) if isinstance(cache.get(did), dict) else None
        ts = _parse_ts(entry.get("fetched_at")) if entry else None
        if entry and ts and now - ts < timedelta(days=ttl_days):
            result[did] = list(entry.get("paragraphs", []))
            continue
        if fetched < max_fetches:
            try:
                paragraphs = parse_description(fetcher(did))
                fetched += 1
                cache[did] = {"fetched_at": now.isoformat(timespec="seconds"), "paragraphs": paragraphs}
                result[did] = paragraphs
                sleep(delay)
                continue
            except Exception as exc:  # noqa: BLE001 - descriptions are best-effort
                print(f"warning: description {did} not fetched: {exc}", file=sys.stderr)
        if entry:
            result[did] = list(entry.get("paragraphs", []))
    return result, fetched


def fetch_description(did: str) -> str:
    return fetch(DESCRIPTION_URL.format(id=int(did)))


# ------------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="site/events.json", help="output path (default: %(default)s)")
    ap.add_argument("--input", help="parse a saved widget response instead of fetching "
                                    "(also skips fetching descriptions)")
    ap.add_argument("--cache", help="JSON file used to cache class descriptions between runs")
    ap.add_argument("--no-descriptions", action="store_true", help="do not fetch class descriptions")
    args = ap.parse_args(argv)

    try:
        js = open(args.input, encoding="utf-8").read() if args.input else fetch(WIDGET_URL)
        events, skipped = build_events(parse_rows(extract_html(js)))
    except ScrapeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    total = len(events) + skipped
    if len(events) < MIN_EVENTS or (total and skipped / total > MAX_SKIPPED_RATIO):
        print(f"error: parse looks broken ({len(events)} events, {skipped} skipped); "
              "not writing output", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    descriptions: dict[str, list[str]] = {}
    if not (args.input or args.no_descriptions):
        cache = load_cache(args.cache)
        descriptions, fetched = collect_descriptions(
            {e["description_id"] for e in events if e["description_id"]}, cache, fetch_description, now)
        save_cache(args.cache, cache)
        print(f"descriptions: {len(descriptions)} classes ({fetched} fetched, "
              f"{len(descriptions) - fetched} from cache)")

    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "source": SCHEDULE_URL,
        "count": len(events),
        "events": events,
        "descriptions": descriptions,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {len(events)} events to {args.out} ({skipped} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
