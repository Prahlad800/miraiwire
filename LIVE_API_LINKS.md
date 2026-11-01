# Mirai Wire ? Public API Links

Base URL: `https://backend-miraiwire.prahlad0227.workers.dev`

All routes below use **GET**. No authentication, request body, or special headers are required. All 10 links were checked on 1 November 2026 and returned HTTP 200.

## Live API links

| Purpose | Request pattern | Working example |
| --- | --- | --- |
| Home news, newest first | `/api/v1/home?page=1&limit=20` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/home?page=1&limit=20) |
| Category news | `/api/v1/home?category=technology&page=1&limit=20` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/home?category=technology&page=1&limit=20) |
| Single news by slug | `/api/v1/news/{slug}` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171) |
| Related news by slug | `/api/v1/news/{slug}/related?limit=6` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171/related?limit=6) |
| Search title and summary | `/api/v1/news/search?q=AI&page=1&limit=20` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/search?q=AI&page=1&limit=20) |
| Search within category | `/api/v1/news/search?q=AI&category=technology` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/search?q=AI&category=technology) |
| Provider-wise RSS feeds | `/api/v1/feeds` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/feeds) |
| Per-feed timing and status | `/api/v1/feeds/details` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/feeds/details) |
| Backend liveness | `/health` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/health) |
| Turso database readiness | `/ready` | [Open API](https://backend-miraiwire.prahlad0227.workers.dev/ready) |

Use the **slug routes** for new detail and related API requests. The examples above use a real saved story:

```text
municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171
```

## How to get a news slug

1. Fetch home, category, or search results.
2. Read the selected story's `slug` and `api_path`.
3. Fetch `BASE_URL + api_path` for details.
4. Fetch `BASE_URL + api_path + "/related?limit=6"` for related stories.

Every story in home, search, category, related, and detail responses includes these fields. Example taken from the live API (other story fields omitted):

```json
{
  "id": 171,
  "title": "Municipal elections conclude peacefully across Chittoor, Annamayya and Sri Sathya Sai districts",
  "slug": "municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171",
  "path": "/news/municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171",
  "api_path": "/api/v1/news/municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171",
  "source": "The Hindu India",
  "category": "india",
  "image_url": "https://th-i.thgim.com/public/incoming/h779u0/article71653366.ece/alternates/LANDSCAPE_1200/10745_1_11_2026_19_27_11_1_IMG_20261101_WA0162.JPG",
  "published_at": "2026-11-01T14:20:25.000Z",
  "fetched_at": "2026-11-01T14:25:54.105Z"
}
```

`api_path` is the backend endpoint. `path` is the intended **frontend page route**; it is not an extra HTML page served by this API.

Slugs contain the title followed by the unique news ID, so identical headlines have different URLs. Copy the returned slug exactly: a wrong title prefix returns HTTP 404. Stored titles are not rewritten by the current RSS ingester.

## Query parameters

| Parameter | Applies to | Default / limits |
| --- | --- | --- |
| `page` | Home, search, related | Default `1`; positive integer |
| `limit` | Home, search, related | Default `20`; range `1?100` |
| `category` | Home and search | Exact category; examples: `technology`, `india`, `world`, `business`, `sports` |
| `q` | Search | Required; 1?200 characters after trimming |
| `{slug}` | Detail and related paths | Exact `slug` returned by the API |

Search performs a literal substring match against title/summary. Related news uses the same category and excludes the selected story. All news APIs read stored Turso records and return only stories with image URLs. Empty category/search results are valid.

## Response formats

Home/category/search return:

```json
{
  "data": [],
  "page": 1,
  "limit": 20,
  "total": 0,
  "total_pages": 0,
  "seo": {}
}
```

This is an abbreviated response shape; `seo` contains dynamic metadata and JSON-LD. A nonempty `data` array contains complete story objects, including `summary`, `url`, and slug fields.

- Detail: `{"data": {...story}, "seo": {...metadata}}`.
- Related: `{"data": [...stories], "page": 1, "limit": 20, "total": 0, "total_pages": 0}`; no top-level SEO object.
- Grouped feeds: top-level `language`, `google_news`, `the_hindu`, `bbc`; each provider has `fetch_interval_minutes`, `last_fetched_at`, `feeds`.
- Feed details: `data` array with per-feed settings, URL, last attempt/success, next due time, last error, and saved count; plus `total`, `language`.
- Liveness: `{"status":"ok"}`.
- Database readiness: `{"status":"ready","database":"turso","news_count":207}` (count is illustrative).

Grouped `last_fetched_at` means the latest successful fetch in that provider, not that every feed succeeded. Check `enabled` and feed details for active feeds. All fetch timestamps are UTC; counts and available stories change over time.

## HTTP status codes

| Status | Meaning |
| --- | --- |
| `200` | Success; empty lists are valid |
| `400` | Invalid page/limit or missing/invalid search query |
| `404` | Missing story, incorrect slug, or unknown route |
| `405` | Unsupported HTTP method |
| `503` | Database unavailable or runtime credentials missing |

CORS preflight `OPTIONS` returns `204`. `/health` checks process liveness; `/ready` checks Turso access.

## SEO metadata and frontend URLs

Detail metadata includes title, description, canonical, Open Graph, Twitter tags, `NewsArticle`, and breadcrumbs. Home/search metadata includes the appropriate collection/search schema. Canonical, schema and breadcrumb story URLs use:

```text
SITE_URL/news/{slug}
```

Set **SITE_URL** in Cloudflare Worker **runtime variables** to the actual frontend origin. The frontend must implement `/news/{slug}` and render the returned metadata/schema in HTML. Do not use a frontend domain that cannot serve that route.

At this check, the live detail canonical was:

```text
https://example.invalid/news/municipal-elections-conclude-peacefully-across-chittoor-annamayya-and-sri-sathya-sai-districts-171
```

**Action required:** the live Worker is using the placeholder frontend origin. Configure SITE_URL before using these canonical URLs for indexing.

## Existing ID links

These remain supported for compatibility:

- [GET /api/v1/news/171](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/171)
- [GET /api/v1/news/171/related?limit=6](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/171/related?limit=6)

They return the same story/related data and slug fields. New integrations should use the returned `api_path`.
