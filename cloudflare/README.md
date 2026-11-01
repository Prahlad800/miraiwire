# Cloudflare Workers deployment

The repository root contains a native JavaScript Worker adapter for the existing
Flask API contract. Python local development stays in `backend/`. Cloudflare uses
`cloudflare/src/index.js`, Turso over HTTPS, and Cron Triggers; no Python process,
Docker container, local database or paid Cloudflare binding is required.

## Cloudflare dashboard (GitHub integration)

1. Workers & Pages > Create application > Connect GitHub.
2. Select `Prahlad800/miraiwire`, production branch `main`.
3. Project name: **backend-miraiwire** (must match wrangler.jsonc).
4. Root directory: repository root `/` (leave the default; do not use backend).
5. Build command: **npm run build**. Cloudflare installs npm dependencies from
   package-lock.json automatically. To reproduce locally first run `npm ci`.
6. Deploy command: **npx wrangler deploy**.
7. Disable Preview builds for this single production database; keep Cloudflare
   Access off for public APIs. If using a non-production upload command later,
   use `npx wrangler versions upload`, not `wrangler preview`.
8. Deploy. The initial deployment can build without credentials; `/health` returns
   200, and DB routes return 503 until the runtime secret is set.
9. Open the created Worker > Settings > Variables and Secrets (runtime settings,
   not the separate build environment). Add **TURSO_AUTH_TOKEN** as a **Secret**,
   using the working database Read & Write token. Never add it to source code.
10. Add **SITE_URL** as a runtime text variable containing the actual public
    frontend origin. Optional: **SITE_LOGO_URL**. Save/deploy these settings.
    wrangler `keep_vars` retains dashboard-only variables on future deployments.
11. Settings > Trigger Events: the source config installs `* * * * *` (every minute,
    UTC). Allow several minutes for a new Cron Trigger to propagate.
12. Check the generated workers.dev URL: `/health`, `/ready`, `/api/v1/home`,
    `/api/v1/feeds/details`. `/ready` must say `database: turso`. Open a returned
    story ID instead of assuming ID 1 exists. Watch Observability logs for
    `RSS scheduled fetch` and a successful `feed_status.last_success_at` update.

Turso URL/engine and public defaults are in wrangler.jsonc. Tokens and SITE_URL
are never required at build time. Copying backend/.env into GitHub is unnecessary.
If the dashboard still has an old build configuration, change it to the commands
above and deploy the latest main commit.

## Cron behavior and free-tier limits

Provider intervals come from grouped `backend/feeds.json`: BBC 15 minutes,
The Hindu 20, Google News 30. Disabled feeds stay disabled (Google currently has
no RSS image entries). The cron checks every minute, claims oldest due feeds
atomically in Turso, then saves image-bearing English entries and feed status.
Default: **one due feed per invocation**, **up to 50 items per feed**, 1 MB RSS
response cap, 15-second RSS timeout. This spreads the eight active feeds across
minutes. Due times are a minimum interval; a backlog delays a feed. Failures
retry after that provider interval. Empty results still count as successful RSS
fetches. `items_saved` counts inserted rows plus missing-image backfills.

RSS image extraction supports media thumbnails/content, image enclosures, and
embedded HTML images. English classification is heuristic (franc-min) and can
reject short/ambiguous English text. Article URLs deduplicate against the same
Turso news table used by Flask. API responses include dynamic SEO metadata.
GET routes only read stored stories; they never fetch external RSS.

No claim of unlimited free capacity: Cloudflare and Turso quotas still apply.
Local runtime tests/dry-run cannot prove deployed free-tier CPU usage. After the
first deployment check CPU time/errors in Observability, especially Cron parsing
and language detection. Adjust feed/item caps if necessary; a paid plan is not
automatically enabled by this repository. No Containers, Queues or paid services
are configured. Public GET APIs use wildcard CORS with no cookies/authentication.

## Local verification

```powershell
npm ci
npm test
npm run build
# Copy .dev.vars.example to .dev.vars, fill the local token and SITE_URL.
npm run dev -- --test-scheduled
```

The Worker runs at http://127.0.0.1:8787. A manual scheduled-event test is
`GET /__scheduled?cron=*+*+*+*+*` on this local test server only; it is not a public
production fetch endpoint. Stop the dev process with Ctrl+C when finished.
`.dev.vars`, backend/.env, node_modules, runtime state and build outputs are ignored.

References:
- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/platform/limits/

Slug URLs: every news object includes `slug`, `path`, `api_path`. Fetch details at
`/api/v1/news/{slug}` and related at `/api/v1/news/{slug}/related`. Numeric ID routes
remain supported. SEO URLs use the frontend route `SITE_URL/news/{slug}`, which
the frontend must implement. Slugs include a unique numeric suffix, allowing
indexed database lookups and avoiding collisions between identical headlines.
