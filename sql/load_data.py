"""
Load the two raw CSVs into a DuckDB database file (treaty.duckdb, in the repo root).

    python sql/load_data.py

Creates two TABLES exactly as generated, plus two cleaned VIEWS that apply the same decisions as notebook 01:
    treaties_raw     -> treaties       cedent names trimmed, inner spaces collapsed, title case
    treaty_year_raw  -> treaty_year    exact duplicate removed, impossible loss ratios (> 3.0) excluded
The queries in this folder read the cleaned views.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "treaty.duckdb"
DATA = ROOT / "data"

con = duckdb.connect(str(DB))
con.execute(f"CREATE OR REPLACE TABLE treaties_raw AS SELECT * FROM read_csv_auto('{(DATA / 'treaties.csv').as_posix()}')")
con.execute(f"CREATE OR REPLACE TABLE treaty_year_raw AS SELECT * FROM read_csv_auto('{(DATA / 'treaty_year.csv').as_posix()}')")

con.execute("""
CREATE OR REPLACE VIEW treaties AS
SELECT * REPLACE (
    -- 'harbourview  LIFE ' -> 'Harbourview Life'
    array_to_string(
        list_transform(string_split(lower(trim(regexp_replace(cedent_name, '\\s+', ' ', 'g'))), ' '),
                       w -> upper(w[1]) || w[2:]),
        ' ') AS cedent_name
)
FROM treaties_raw
""")
con.execute("""
CREATE OR REPLACE VIEW treaty_year AS
SELECT DISTINCT *
FROM treaty_year_raw
WHERE claims_paid / premium_earned <= 3.0
""")

for name in ["treaties_raw", "treaty_year_raw", "treaties", "treaty_year"]:
    n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"{name:<16} {n:>5} rows")
print("distinct cedents after cleaning:", con.execute("SELECT COUNT(DISTINCT cedent_name) FROM treaties").fetchone()[0])
con.close()
print(f"Wrote {DB.name}")
