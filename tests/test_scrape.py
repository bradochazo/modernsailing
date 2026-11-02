"""Offline tests for scripts/scrape.py (no network).

The fixture mirrors the real widget markup: regular rows, an "underway" row,
a series summary row followed by child rows, and a non-ASCII instructor name.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import scrape  # noqa: E402


def regular(tr_id, item, date, time, days, title, boat, loc, signup="", extra_cls=""):
    button = (f'<a class="hc-button signup_now" target="_blank" href="{signup}">Sign Up</a>'
              if signup else "")
    return f"""
<tr class="odd filterable {extra_cls}" id="{tr_id}" data-hc-id="{tr_id}" data-hc-mbo-class="1">
  <td class="healcode-date-field"> {date} </td>
  <td class="healcode-time-field"> {time} </td>
  <td class="healcode-days-field"> {days} </td>
  <td class="healcode-button-field"><span class="healcode-time-value">{button}</span></td>
  <td class="mbo_class"><span class="classname" id="item_{item}_mbo_class"><a data-url="https://widgets.mindbodyonline.com/widgets/class_lists/x/class_description?class_description_id=1" href="">{title}</a></span></td>
  <td class="trainer"><span class="trainer"><a href="">{boat}</a></span></td>
  <td class="location"><span class="location">{loc}</span></td>
</tr>"""


def child(tr_id, item, date, time, days, title, boat, loc):
    return f"""
<tr class="even filterable child" id="{tr_id}">
  <td class="healcode-date-field"> {date} </td>
  <td class="healcode-time-field"> {time} </td>
  <td class="healcode-days-field"> {days} </td>
  <td class="healcode-button-field"> </td>
  <td class="mbo_class"><span class="classname" id="item_{item}_mbo_class"><a href="">{title}</a></span></td>
  <td class="trainer"><span class="trainer"><a href="">{boat}</a></span></td>
  <td class="location"><span class="location">{loc}</span></td>
</tr>"""


SERIES_SIGNUP = "https://clients.mindbodyonline.com/ws.asp?sclassid=12095&amp;studioid=21775"
CLUB_SIGNUP = "https://clients.mindbodyonline.com/ws.asp?sclassid=11970&amp;studioid=21775"

TABLE = "<table class='enrollments'><tr><th>Dates</th><th>Times</th><th>Days</th></tr>" + "".join([
    regular("1", "12109", "Oct 31 2026 - Nov 08 2026", "9:00 AM -  3:30 PM", "Sat, Sun",
            "ASA 101, Basic Keelboat Sailing (Cruising)", "Eric Wittig", "Berkeley",
            extra_cls="healcode-underway"),
    regular("2", "11934", "Nov 02 2026 - Nov 06 2026", "9:00 AM -  4:30 PM",
            "Mon, Tue, Wed, Thu, Fri",
            "ASA 101/103, Basic Keelboat Sailing &amp; Basic Coastal Cruising Combination Course",
            "Wolfgang Hausen", "Sausalito"),
    regular("3", "11970", "Nov 05 2026", "10:00 AM -  3:30 PM", "Thu",
            "Club Sail - Weekday Prime Time - Thursday", "Liberty *Beneteau 38", "Sausalito",
            signup=CLUB_SIGNUP),
    regular("4", "11999", "Nov 06 2026 - Nov 08 2026", "9:00 AM -  3:30 PM", "Fri, Sat, Sun",
            "ASA 104, Bareboat Cruising", "J\u00f6rg Chabowski", "Sausalito"),
    # series: summary row then children, followed by a regular row that ends the block
    f"""<tr class="even filterable healcode-summary-course" id="9" data-hc-id="9" data-hc-mbo-class="429 430">
  <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
  <td class="healcode-button-field"><span class="healcode-time-value"><a class="hc-button signup_now" href="{SERIES_SIGNUP}">Sign Up</a></span></td>
  <td>Level 2: Mymble BYC Chowder Series</td><td>&nbsp;</td></tr>""",
    child("c1", "12095", "Nov 08 2026", "11:00 AM - 4:00 PM", "Sun",
          "Training - Development Race Team Practice Session", "David Scott", "Berkeley"),
    child("c2", "12095", "Nov 22 2026", "11:00 AM - 4:00 PM", "Sun",
          "Regatta - BYC Sunday Chowder Race (Development Race Team)", "David Scott", "Berkeley"),
    regular("5", "12141", "Nov 04 2026", "9:00 AM -  3:00 PM", "Wed",
            "Private Lesson + Checkout ", "Tyler Cobbett", "Sausalito", signup=CLUB_SIGNUP),
]) + "</table>"


def widget_js(html: str) -> str:
    """Wrap HTML the way Healcode does: a single-quoted JS string with escapes."""
    esc = (html.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
           .replace("\n", "\\n").replace("/", "\\/"))
    # non-ASCII as \uXXXX, like many JS serialisers
    esc = "".join(c if ord(c) < 128 else f"\\u{ord(c):04x}" for c in esc)
    return f"hcjq(function($){{\n  $('div#hc_enrollments_x').html('{esc}');\n}});\n"


class ScrapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = scrape.extract_html(widget_js(TABLE))
        cls.events, cls.skipped = scrape.build_events(scrape.parse_rows(html))
        cls.by_title = {}
        for e in cls.events:
            cls.by_title.setdefault(e["title"], []).append(e)

    def test_counts(self):
        # 5 regular + 2 child rows; the summary row is not an event
        self.assertEqual(len(self.events), 7)
        self.assertEqual(self.skipped, 0)

    def test_js_unescape_roundtrip(self):
        html = scrape.extract_html(widget_js(TABLE))
        self.assertIn("J\u00f6rg Chabowski", html)
        self.assertIn("Basic Coastal Cruising Combination Course", html)

    def test_extract_requires_payload(self):
        with self.assertRaises(scrape.ScrapeError):
            scrape.extract_html("console.log('nothing here')")

    def test_multi_day_course(self):
        e = self.by_title["ASA 101/103, Basic Keelboat Sailing & Basic Coastal Cruising Combination Course"][0]
        self.assertEqual((e["start"], e["end"]), ("2026-11-02", "2026-11-06"))
        self.assertEqual(e["days"], [0, 1, 2, 3, 4])
        self.assertEqual(e["day_kind"], "week")
        self.assertEqual(e["time_label"], "9:00 AM – 4:30 PM")
        self.assertEqual(e["start_bucket"], "morning")
        self.assertEqual(e["category"], "ASA Courses")
        self.assertFalse(e["available"])
        self.assertEqual(e["signup_url"], "")

    def test_underway_and_weekend(self):
        e = self.by_title["ASA 101, Basic Keelboat Sailing (Cruising)"][0]
        self.assertTrue(e["underway"])
        self.assertEqual(e["day_kind"], "weekend")
        self.assertEqual(e["start"], "2026-10-31")

    def test_mixed_days_and_unicode(self):
        e = self.by_title["ASA 104, Bareboat Cruising"][0]
        self.assertEqual(e["day_kind"], "mixed")
        self.assertEqual(e["boat"], "J\u00f6rg Chabowski")

    def test_signup_link(self):
        e = self.by_title["Club Sail - Weekday Prime Time - Thursday"][0]
        self.assertTrue(e["available"])
        self.assertTrue(e["signup_url"].startswith("https://clients.mindbodyonline.com/"))
        self.assertIn("&studioid=21775", e["signup_url"])  # entity decoded
        self.assertEqual(e["category"], "Club Sails")
        self.assertEqual(e["series"], "")

    def test_series_children_inherit(self):
        for title in ("Training - Development Race Team Practice Session",
                      "Regatta - BYC Sunday Chowder Race (Development Race Team)"):
            e = self.by_title[title][0]
            self.assertEqual(e["series"], "Level 2: Mymble BYC Chowder Series")
            self.assertTrue(e["available"])
            self.assertIn("sclassid=12095", e["signup_url"])
            self.assertEqual(e["category"], "Racing")

    def test_series_does_not_leak_to_next_regular_row(self):
        e = self.by_title["Private Lesson + Checkout"][0]  # trailing space stripped
        self.assertEqual(e["series"], "")
        self.assertEqual(e["category"], "Checkouts")
        self.assertTrue(e["signup_url"].endswith("studioid=21775"))

    def test_ids_unique_and_stable(self):
        ids = [e["id"] for e in self.events]
        self.assertEqual(len(ids), len(set(ids)))
        # same series item on different dates must not collide
        race = [e["id"] for e in self.by_title["Training - Development Race Team Practice Session"]
                + self.by_title["Regatta - BYC Sunday Chowder Race (Development Race Team)"]]
        self.assertEqual(len(race), len(set(race)))
        self.assertTrue(all(i.startswith("12095-") for i in race))

    def test_sorted_by_start(self):
        keys = [(e["start"], e["start_time"]) for e in self.events]
        self.assertEqual(keys, sorted(keys))

    def test_categories(self):
        c = scrape.categorize
        self.assertEqual(c("Checkout - Fleet Rating - Sportboat Group"), "Checkouts")
        self.assertEqual(c("2027 - Belize - Flotilla"), "Trips")
        self.assertEqual(c("2027 - Greece - Info Session"), "Talks & Info")
        self.assertEqual(c("Development Sail - Silver Fleet"), "Development Sails")
        self.assertEqual(c("Orientation Sail - Berkeley"), "Intro & Orientation")
        self.assertEqual(c("Introductory Sail"), "Intro & Orientation")
        self.assertEqual(c("Night Sailing Clinic"), "Clinics")
        self.assertEqual(c("Upgrade to Silver Fleet Clinic"), "Clinics")
        self.assertEqual(c("Custom ASA 101, Basic Keelboat"), "ASA Courses")
        self.assertEqual(c("Something New"), "Other")

    def test_bad_row_is_skipped_not_fatal(self):
        bad = TABLE.replace("Nov 05 2026", "TBD")
        events, skipped = scrape.build_events(scrape.parse_rows(
            scrape.extract_html(widget_js(bad))))
        self.assertEqual(skipped, 1)
        self.assertEqual(len(events), 6)

    def test_fetch_refuses_other_hosts(self):
        with self.assertRaises(scrape.ScrapeError):
            scrape.fetch("https://example.com/widgets/enrollments/x")
        with self.assertRaises(scrape.ScrapeError):
            scrape.fetch("http://widgets.mindbodyonline.com/widgets/enrollments/x")


# Real markup captured from the widget's class_description pages (trimmed).
DESC_SPANS = (
    '<html><body><script>var x="<div>nope</div>";</script><h1>ignored title</h1>'
    '<div class="class_description"><div><span style="font-size:14px;">San Francisco Bay\'s famous wind, '
    'strong currents, and more.&nbsp;This course provides the skills you need.</span></div>'
    '<div><span style="font-size:14px;">&nbsp;</span></div>'
    '<div><span style="font-size:14px;">Your official ASA logbook and the<em> Sailing Made Easy</em> textbook '
    'are included. Please <a href="https://www.modernsailing.com/contact">contact our office</a>.</span></div>'
    '<div><span style="font-size:14px;">&nbsp;</span></div>'
    '<div> <span style="font-size:14px;"><strong>Price</strong>: Members $1025 / Non-members $1260</span></div>'
    '<div> <span style="font-size:14px;"><strong>Prerequisites</strong>: None</span><br>'
    '<span style="font-size:14px;"><strong>Max Capacity</strong>: 4 students</span> </div></div>'
    '<div class="other">not part of the description</div></body></html>')
DESC_PARAS = (
    '<div class="class_description"><div>All new, returning, or current members must complete a skills '
    'checkout.<p>Before a checkout can be scheduled, our office will review your resume.</p> '
    '<p>During the checkout, you will demonstrate key skills.</p> </div></div>')


class DescriptionTests(unittest.TestCase):
    def test_parse_span_layout(self):
        lines = scrape.parse_description(DESC_SPANS)
        self.assertEqual(lines[0], "San Francisco Bay's famous wind, strong currents, and more. "
                                   "This course provides the skills you need.")
        self.assertEqual(lines[1], "Your official ASA logbook and the Sailing Made Easy textbook are "
                                   "included. Please contact our office.")
        self.assertEqual(lines[2:], ["Price: Members $1025 / Non-members $1260", "Prerequisites: None",
                                     "Max Capacity: 4 students"])  # <br> splits lines; blank spacer divs dropped

    def test_parse_paragraph_layout(self):
        lines = scrape.parse_description(DESC_PARAS)
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("All new, returning"))
        self.assertTrue(lines[1].startswith("Before a checkout"))

    def test_ignores_script_and_other_blocks(self):
        text = " ".join(scrape.parse_description(DESC_SPANS))
        self.assertNotIn("nope", text)
        self.assertNotIn("ignored title", text)
        self.assertNotIn("not part of the description", text)

    def test_no_description_block(self):
        self.assertEqual(scrape.parse_description("<html><body><h1>x</h1></body></html>"), [])

    def test_description_id_on_events(self):
        events, _ = scrape.build_events(scrape.parse_rows(scrape.extract_html(widget_js(TABLE))))
        regular_ids = {e["description_id"] for e in events if "Private Lesson" in e["title"]}
        self.assertEqual(regular_ids, {"1"})   # parsed from ...class_description_id=1

    def _fetcher(self, calls, fail=()):
        def fetch(did):
            calls.append(did)
            if did in fail:
                raise OSError("boom")
            return f'<div class="class_description"><div>Text for {did}</div></div>'
        return fetch

    def test_only_missing_ids_are_fetched(self):
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        cache = {"1": {"fetched_at": (now - timedelta(days=1)).isoformat(), "paragraphs": ["cached one"]}}
        calls = []
        res, fetched = scrape.collect_descriptions({"1", "2", "x"}, cache, self._fetcher(calls), now,
                                                   sleep=lambda s: None)
        self.assertEqual(calls, ["2"])                      # "1" fresh in cache, "x" not numeric
        self.assertEqual(res, {"1": ["cached one"], "2": ["Text for 2"]})
        self.assertEqual(fetched, 1)
        self.assertIn("2", cache)                           # cache updated in place

    def test_stale_entries_refetched(self):
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        cache = {"1": {"fetched_at": "2026-11-02T00:00:00+00:00", "paragraphs": ["old"]}}
        calls = []
        res, _ = scrape.collect_descriptions({"1"}, cache, self._fetcher(calls), now, sleep=lambda s: None)
        self.assertEqual(calls, ["1"])
        self.assertEqual(res["1"], ["Text for 1"])

    def test_failed_fetch_falls_back_to_stale_copy(self):
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        cache = {"1": {"fetched_at": "2026-11-02T00:00:00+00:00", "paragraphs": ["old"]}}
        calls = []
        res, fetched = scrape.collect_descriptions({"1", "2"}, cache, self._fetcher(calls, fail={"1", "2"}),
                                                   now, sleep=lambda s: None)
        self.assertEqual(res, {"1": ["old"]})               # "2" has no copy -> omitted, run continues
        self.assertEqual(fetched, 0)

    def test_fetch_cap(self):
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        calls = []
        res, fetched = scrape.collect_descriptions({"1", "2", "3"}, {}, self._fetcher(calls), now,
                                                   max_fetches=2, sleep=lambda s: None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(res), 2)

    def test_cache_roundtrip_and_corruption(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "c.json")
            scrape.save_cache(path, {"1": {"fetched_at": "x", "paragraphs": ["a"]}})
            self.assertEqual(scrape.load_cache(path)["1"]["paragraphs"], ["a"])
            with open(path, "w") as fh:
                fh.write("{not json")
            self.assertEqual(scrape.load_cache(path), {})
            self.assertEqual(scrape.load_cache(os.path.join(d, "missing.json")), {})
            self.assertEqual(scrape.load_cache(None), {})


if __name__ == "__main__":
    unittest.main()
