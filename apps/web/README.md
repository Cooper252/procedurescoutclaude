# ProcedureScout website

Next.js (App Router) + TypeScript. Mobile first, English and Spanish.

```
npm ci
npm run typecheck
npm run build
npm start                         # http://localhost:3000, preview data
API_URL=http://localhost:8000 npm run build && npm start   # real API through /api
```

Without `API_URL` the site uses `lib/synthetic_demo.ts`: made-up "Sample …" facilities and prices, with a "Preview" bar on every page. They never reach the API or the database.

Pages: `/` home, `/search` results, `/help-paying`, `/bill`, `/how-it-works`. Design tokens are at the top of `app/globals.css`.
