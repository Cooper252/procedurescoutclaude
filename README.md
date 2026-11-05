# ProcedureScout

U.S. hospital price transparency platform. Nevada first, built for national scale.

**No price is better than a false price.**

Start with `CLAUDE.md` (rules for contributors and AI agents) and `docs/PROGRESS.md` (what is actually done).

```
make setup && make up && make migrate && make check
```

Without Docker: install PostgreSQL 16 + PostGIS 3.4, run `scripts/db_init.sql` as a superuser, copy `.env.example` to `.env`, then `make migrate && make check`.
