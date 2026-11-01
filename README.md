# Miraiwire

Miraiwire project repository.

## Backend

The Flask backend and its `/health` endpoint are in [backend](./backend/README.md).

## Cloudflare deployment

Use the repository-root Workers adapter and [Cloudflare deployment guide](cloudflare/README.md).
Dashboard project: `backend-miraiwire`; root `/`; build `npm run build`; deploy
`npx wrangler deploy`. Set the Turso token as a Worker runtime Secret after the
initial deployment. Python local development continues in `backend/`.
