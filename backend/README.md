# Miraiwire news backend

100 configurable Google News topic RSS URLs are in `feeds.json` (20 each:
technology, india, world, business, sports). These are topic feeds, not 100
independent publishers. RSS availability depends on the provider.

## Run on Windows

From `backend` in two terminals:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

```powershell
.\.venv\Scripts\python.exe worker.py
```

The worker checks for due feeds every 30 seconds. Each feed is fetched initially,
then every 30 minutes by default. Change `fetch_interval_minutes` in `feeds.json`;
the next worker cycle reloads config (already scheduled due times remain until
that next fetch). Run only one worker. It must stay running for automatic fetches.
For a one-time pass over due feeds: `python worker.py --once`.
Five concurrent requests, 15 second request timeout, up to 100 items per feed.
Individual failures are recorded and retried at the next interval; other feeds continue.

SQLite file: `backend/data/news.sqlite3` (excluded from Git).
Override with the `NEWS_DATABASE` environment variable. The `news` table stores
stories, deduplicated globally by URL. `feed_status` stores last attempt/success,
next fetch, last error and newly inserted count for each feed. All dates use UTC.
Existing stories survive restarts. No full-article scraping: summary and optional
image depend on RSS availability; Google URLs can lead through a redirect.

## Public GET APIs

Base URL: `http://127.0.0.1:5000`. No authentication, body or special headers required.

| Purpose | Request |
| --- | --- |
| Home, newest first | `/api/v1/home?page=1&limit=20` |
| Category filter | `/api/v1/home?category=technology&page=1&limit=20` |
| Single story | `/api/v1/news/1` |
| Related (same category, excludes current story) | `/api/v1/news/1/related?limit=6` |
| Search title/summary | `/api/v1/news/search?q=AI&page=1&limit=20` |
| Search category | `/api/v1/news/search?q=AI&category=technology` |
| Liveness | `/health` |

Home/search/related response, HTTP 200 (illustrative values):

```json
{
  "data": [{
    "id": 1,
    "title": "Example technology news",
    "url": "https://example.com/story",
    "summary": "RSS summary in plain text",
    "source": "Example Publisher",
    "category": "technology",
    "image_url": null,
    "published_at": "2026-11-01T10:00:00+00:00",
    "fetched_at": "2026-11-01T10:05:00+00:00"
  }],
  "page": 1,
  "limit": 20,
  "total": 1,
  "total_pages": 1
}
```

Single story returns `{"data": {...same story fields...}}`.
Empty lists return HTTP 200 with `data: []`, `total: 0`, `total_pages: 0`.
Missing story/related ID: HTTP 404, `{"error":"News not found"}`.
Invalid page/limit: HTTP 400, `{"error":"Invalid request parameters"}`.
Missing/blank/overlong search: HTTP 400, `{"error":"q is required (1-200 characters)"}`.
Page starts at 1; limit is 1-100. Search is a literal substring; SQLite default
LIKE case folding applies (ASCII case-insensitive). Related uses category, not
semantic similarity. `/health` reports process liveness, not feed freshness.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Turso online database and environment

Copy `.env.example` to `.env` and set:

```dotenv
DATABASE_DRIVER=turso
TURSO_DATABASE_URL=libsql://YOUR-DATABASE-YOUR-ORG.turso.io
TURSO_AUTH_TOKEN=YOUR_DATABASE_TOKEN
TURSO_DATABASE_ENGINE=libsql
SITE_URL=https://YOUR-FRONTEND-DOMAIN
SITE_NAME=Mirai Wire
SITE_LOGO_URL=https://YOUR-FRONTEND-DOMAIN/logo.png
RSS_GOOGLE_FETCH_MINUTES=30
RSS_THE_HINDU_FETCH_MINUTES=20
RSS_BBC_FETCH_MINUTES=15
RSS_ENGLISH_ONLY=true
```

Use `TURSO_DATABASE_ENGINE=turso` for the new Turso engine (`turso://` URL).
Remote queries use HTTPS SQL-over-HTTP (v2 libSQL / v3 Turso). Credentials stay
on the backend. Never expose the token as a public frontend variable.
With driver `turso`, API and worker read/write the same online database directly;
there is no silent fallback to SQLite. Tables/indexes are initialized on startup.
Existing local stories are not automatically uploaded. A new remote database is
populated by the worker; run both processes with the same `.env` and restart both
after environment changes. With driver `sqlite`, local development continues.
No real Turso credentials are included. Live remote connection needs your URL/token.
Remote individual SQL statements autocommit; a feed may save some stories before
a failure. Retries skip existing URLs and safely continue.

Feed catalog now has **108 English feeds**: original 100 Google News topic feeds,
4 direct BBC and 4 direct The Hindu section feeds. English language detection runs
on new titles/summaries and skips detected other languages; short texts can be
misclassified. It does not translate or retroactively clean existing stored rows.
Provider intervals above override JSON defaults. Individual feed JSON interval
can be used when the provider environment override is unset. Changed intervals
apply to due-time calculation on the next worker check.

`GET /api/v1/feeds` returns every feed's provider, URL, configured fetch interval,
last attempt, last success, next fetch, last error and items saved.
`GET /ready` checks the selected database and returns its mode and story count
(HTTP 503 on failure). `/health` remains process liveness only.

## Dynamic SEO metadata and schema

Home, category, search responses now include a top-level `seo` object. Single-news
responses include `seo` generated from that story. Existing `data` fields remain.

```json
{
  "data": {"id": 42, "title": "Example news", "summary": "RSS description"},
  "seo": {
    "title": "Example news | Mirai Wire",
    "description": "RSS description",
    "canonical": "https://YOUR-FRONTEND-DOMAIN/news/42/example-news",
    "language": "en",
    "robots": "index,follow,max-image-preview:large",
    "open_graph": {"og:type": "article", "og:title": "Example news | Mirai Wire"},
    "twitter": {"twitter:card": "summary"},
    "json_ld": [
      {"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Example news"},
      {"@context": "https://schema.org", "@type": "BreadcrumbList"}
    ]
  }
}
```

Illustration shortened above; actual schema includes headline, description,
canonical page, category, English language, publish time, source publisher and
original article URL (`isBasedOn`); image is included only when present. No fake
author, image or modified date is generated. Fetch time is not publish/update time.
Home provides `WebSite` + `CollectionPage` + `ItemList`; categories provide
`CollectionPage` + `ItemList`; search provides `SearchResultsPage` and `noindex`.
Descriptions use feed text with a 160-character budget and title fallback.

Frontend must implement `/news/{id}/{slug}`, category and `/search` routes, render
these values into the HTML `<head>` (title/meta/canonical/Open Graph/Twitter), and
render each JSON-LD entry in `<script type="application/ld+json">`. Escape HTML
attributes and safely serialize JSON-LD (escape `<` as `\u003c`). API JSON by itself
does not install SEO tags on a website. Configure SITE_URL to the real frontend,
not the API host. Metadata/schema describe the content shown, crediting original
publishers. This backend does not create a frontend, scrape full paid articles,
or guarantee search ranking or rich results.

References: https://docs.turso.tech/sdk/python/quickstart and
https://developers.google.com/search/docs/appearance/structured-data/article

### Grouped provider JSON

`GET /api/v1/feeds` groups feeds under `google_news`, `the_hindu`, `bbc`, alongside
`language: en`. Each provider includes `fetch_interval_minutes`, `last_fetched_at`,
and `feeds` (id, name, category, enabled, provider, language). RSS URLs are retained
in feeds.json. `last_fetched_at` is the latest successful feed fetch within that
provider in UTC, or null before any successful fetch; it does not mean all feeds
in the provider succeeded. `GET /api/v1/feeds/details` provides the full flat list,
RSS URLs and per-feed attempt/success/error/next-fetch status.

### Grouped config and image-only news

`feeds.json` itself now uses top-level `language`, `google_news`, `the_hindu`,
`bbc`. Each provider has `fetch_interval_minutes`, `last_fetched_at: null`, `feeds`.
Each feed retains `url` so the worker can fetch it. Config timestamps are placeholders;
SQLite/Turso feed_status is the authority for dynamic API `last_fetched_at`.

Only feeds with image entries in the local live audit are enabled: 4 BBC and
4 The Hindu feeds. The 100 Google News feeds are retained but disabled because
none contained image entries in that audit. Re-enable only after verifying image
support. The ignored `data/image-feed-audit.json` contains the per-feed audit.

Ingestion requires an HTTP(S) image URL from RSS media content, thumbnail,
image enclosure, or embedded summary/content img. No article-page scraping and
no placeholder images are used. Availability of the remote image is not guaranteed.
Existing stories without images remain stored but are hidden by home, search,
detail and related APIs; direct IDs without images return 404. Re-fetched existing
URLs can gain missing images. Environment provider intervals still override JSON.

### Automatic schedule and database-backed APIs

`feeds.json` provider `fetch_interval_minutes` is authoritative (per-feed override
wins if supplied); environment timing values are fallback only when JSON does not
supply a provider interval. The worker reloads JSON every cycle and checks due feeds
every 30 seconds. An enabled feed is due at last_attempt_at + its interval; a feed
with no attempt is immediately due. Failed attempts retry after the same interval.
Successful fetches save image-bearing English stories and timestamps in the database;
duplicate URLs are skipped. Feed timestamps survive process restarts. The continuous
worker retries transient cycle failures instead of stopping permanently.

Home/category, single story, related, search/category search all SELECT from the
configured database. GET requests do not fetch external RSS. `/health` is process
liveness; `/ready` checks database access; `/api/v1/feeds/details` shows individual
last attempt/success/error/next due time. Both API and worker must remain running
for automatic ingestion. The check loop may start a fetch up to roughly 30 seconds
after its due time (plus any ongoing network work). Disabled feeds do not fetch.

Slug detail and related APIs are supported: `/api/v1/news/{slug}` and
`/api/v1/news/{slug}/related`. Every news object includes `slug`, `path`, `api_path`.
Existing numeric ID APIs continue to work. The slug is title text (up to 100 ASCII
characters) followed by the unique news ID, with `news` as the empty-title fallback.
SEO canonical, schema, breadcrumbs and list URLs use `SITE_URL/news/{slug}`;
the frontend must render that route. Titles are not rewritten by the RSS ingester.
