# Modern Sailing schedule

A free, filterable view of the public schedule at <https://www.modernsailing.com/schedule>.

- `scripts/scrape.py` downloads the club's Mindbody schedule widget and writes `site/events.json` (Python standard library only).
- `site/index.html` is a static page (no build step) that reads `events.json` and lists events by month with filters for type, location, day of week, start time, availability, favorited events and text search. Filter choices and favorites are remembered in the visitor's browser. A Business / Party switch at the top right changes the look (Party is a deliberately tacky late-90s tropical skin).
- `scripts/make_party_gifs.py` redraws the animated GIFs in `site/party/` (needs Pillow; the GIFs are committed, so the site build doesn't need it).
- `.github/workflows/update-schedule.yml` re-scrapes every 4 hours and publishes the site to GitHub Pages. Cost: $0.

## Set up (about 5 minutes)

1. Create a **public** GitHub repository and push this folder to its `main` branch.
2. In the repo go to **Settings → Pages** and set **Source** to **GitHub Actions**.
3. Open the **Actions** tab, choose **Update schedule site**, and click **Run workflow**.
4. When it finishes, the site is at `https://<your-username>.github.io/<repo-name>/`.

After that it refreshes itself. The workflow's logs show a line like `wrote 145 events to site/events.json`.

## Run locally

```bash
python3 -m unittest discover -s tests -v      # offline parser tests
python3 scripts/scrape.py --out site/events.json --cache .cache/descriptions.json
python3 -m http.server -d site 8000            # open http://localhost:8000
```

## How it works

The club's page embeds a Mindbody "Healcode" enrollments widget (ID `db8098683b`). The widget is a small JavaScript file that sets an HTML table, so `scrape.py` decodes that string and parses the rows. Three row types exist: regular events, race-series summary rows, and "child" rows (the individual race sessions, which inherit the series name and sign-up link).

## Things to know

- **Be polite.** Every 4 hours the workflow makes one request for the schedule. Class descriptions (shown under "View details") are fetched one request per class and cached for 7 days, so after the first run only a handful of extra requests happen per week. Please don't make it much more frequent.
- **Descriptions are plain text.** Links and bold in the club's description pages are dropped; "Price", "Duration" etc. lines keep their labels. Use `--no-descriptions` to skip them.
- **Scheduled workflows pause** after 60 days without repository activity on public repos. If updates stop, re-enable the workflow in the Actions tab or push any commit.
- **If the club changes its widget**, the scraper refuses to publish when fewer than 20 events parse or more than 10% of rows fail, so the last good site stays up. Check the failed run's log.
- **Categories** (ASA Courses, Club Sails, Racing, …) are assigned by title in `categorize()` in `scrape.py`. Edit it if the club adds new event names. Unknown titles show as "Other".
- **Time-of-day buckets** (`start_bucket()`): before noon = Morning, noon to 4 pm = Afternoon, 4 pm or later = Evening.
- **Favorites and filter choices** are stored in your own browser (localStorage) and aren't shared across devices.
- This is an unofficial view. Availability shown is only whether a sign-up link is listed; confirm with the club.
