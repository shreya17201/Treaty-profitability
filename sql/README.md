# SQL layer

The same portfolio questions as the notebooks, answered in SQL against a local DuckDB file. DuckDB runs from a
single file with no server, and the SQL here is standard enough to run on Snowflake or Postgres with little change.

## Run it

From the repo root, with the virtual environment active:

```bash
python generate_data.py              # if data/ is empty
python sql/load_data.py              # CSVs -> treaty.duckdb (raw tables + cleaned views)
python sql/run.py 01_portfolio_summary.sql
python sql/run.py 02_loss_ratio_by_treaty.sql --rows 30
python sql/run.py 03_worst_performers.sql
```

## What is in the database

| Object | Type | What it is |
|---|---|---|
| `treaties_raw`, `treaty_year_raw` | table | the CSVs exactly as generated |
| `treaties` | view | cedent names cleaned (trimmed, single spaces, title case) |
| `treaty_year` | view | exact duplicate removed, loss ratios above 3.0 excluded (same decisions as notebook 01) |

## The queries

| File | Question | SQL shown |
|---|---|---|
| `01_portfolio_summary.sql` | How is the whole book doing each year? | `GROUP BY`, computed ratio, `COUNT(*) FILTER (WHERE ...)` |
| `02_loss_ratio_by_treaty.sql` | How is each treaty trending? | window functions: running `AVG() OVER (PARTITION BY ... ORDER BY ...)`, `LAG` |
| `03_worst_performers.sql` | Which treaties lose the most money? | CTEs, `ROW_NUMBER`, join, `RANK`, `NTILE(4)` |

The SQL and the notebooks answer overlapping questions on purpose: the SQL is what a data team would run against a
warehouse; the notebooks are the analysis. `treaty.duckdb` is generated and is not committed (see `.gitignore`).
