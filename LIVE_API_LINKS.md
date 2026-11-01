# Mirai Wire — Public API Links

Base URL: `https://backend-miraiwire.prahlad0227.workers.dev`

All endpoints use **GET**. No authentication, request body, or special headers are required.

| Purpose | Live API link |
| --- | --- |
| Home news, newest first | [GET /api/v1/home?page=1&limit=20](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/home?page=1&limit=20) |
| Category news | [GET /api/v1/home?category=technology&page=1&limit=20](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/home?category=technology&page=1&limit=20) |
| Single news | [GET /api/v1/news/171](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/171) |
| Related news | [GET /api/v1/news/171/related?limit=6](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/171/related?limit=6) |
| Search title and summary | [GET /api/v1/news/search?q=AI&page=1&limit=20](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/search?q=AI&page=1&limit=20) |
| Search within category | [GET /api/v1/news/search?q=AI&category=technology](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/news/search?q=AI&category=technology) |
| Provider-wise RSS feeds | [GET /api/v1/feeds](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/feeds) |
| Per-feed fetch timing and status | [GET /api/v1/feeds/details](https://backend-miraiwire.prahlad0227.workers.dev/api/v1/feeds/details) |
| Backend liveness | [GET /health](https://backend-miraiwire.prahlad0227.workers.dev/health) |
| Turso database readiness | [GET /ready](https://backend-miraiwire.prahlad0227.workers.dev/ready) |

## Parameters

| Parameter | Meaning | Default / limits |
| --- | --- | --- |
| `page` | Page number for home, search, and related lists | Default `1`; minimum `1` |
| `limit` | Records per page | Default `20`; range `1–100` |
| `category` | Exact category filter on home and search | `technology`, `india`, `world`, `business`, `sports` |
| `q` | Search title and summary | Required for search; 1–200 characters after trimming |
| News ID in path | ID returned by home/search APIs | Replace example `171` with the desired ID |

Stories are read from Turso. News responses include only records with image URLs.
Related news uses the same category and excludes the current story. Home, search,
and detail responses also include a `seo` object with metadata and JSON-LD.
Feed configuration does not imply every provider is enabled; inspect `enabled`
and the fetch status endpoints for current settings.

## Responses

- `200`: Success. Empty lists return `data: []`, `total: 0`, `total_pages: 0`.
- `400`: Invalid pagination or missing/invalid search query.
- `404`: Missing news record or unknown endpoint.
- `405`: Unsupported HTTP method. CORS preflight `OPTIONS` returns `204`.
- `503`: Database unavailable or credentials not configured.

List response:

```json
{
  "data": [],
  "page": 1,
  "limit": 20,
  "total": 0,
  "total_pages": 0
}
```

Single news response: `{"data": {...}, "seo": {...}}`.

Liveness response: `{"status":"ok"}`.

Database readiness response (illustrative count):

```json
{"status":"ready","database":"turso","news_count":207}
```

`/health` checks the backend process; `/ready` checks database access. Counts,
news IDs, feed timestamps, and available stories change as scheduled fetching runs.
Fetch timestamps use UTC.

## Slug-based news URLs

Home, category, search, related, and detail story objects include `slug`, `path`
and `api_path`. For example, title "AI launch", ID 171 produces:

```json
{
  "id": 171,
  "slug": "ai-launch-171",
  "path": "/news/ai-launch-171",
  "api_path": "/api/v1/news/ai-launch-171"
}
```

Use `api_path` returned by the API for the real title; the example above is
illustrative. Detail: `GET /api/v1/news/{slug}`. Related:
`GET /api/v1/news/{slug}/related?limit=6`. Existing numeric ID URLs still work.
Incorrect title prefixes return 404 rather than serving another canonical slug.
The numeric suffix makes identical headlines unique and keeps lookups indexed by
primary key without scanning the database. Slugs derive from stored titles, which
the current ingester does not rewrite. No database migration is required.

SEO canonical, Open Graph URL, NewsArticle URLs, breadcrumbs and ItemList links
now use `SITE_URL/news/{slug}`. The frontend must implement that page route and
render returned SEO tags in HTML; API JSON alone does not publish a web page.
