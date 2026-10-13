"""
Run one .sql file against treaty.duckdb and print the result as a table.

    python sql/run.py 01_portfolio_summary.sql
    python sql/run.py 02_loss_ratio_by_treaty.sql --rows 30
"""
import argparse
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "treaty.duckdb"

parser = argparse.ArgumentParser(description="Run a SQL file against treaty.duckdb")
parser.add_argument("file", help="e.g. 01_portfolio_summary.sql (looked up in sql/ if not found as given)")
parser.add_argument("--rows", type=int, default=20, help="maximum rows to print (default 20)")
args = parser.parse_args()

path = Path(args.file)
if not path.exists():
    path = Path(__file__).resolve().parent / args.file
if not DB.exists():
    raise SystemExit("treaty.duckdb not found. Run:  python sql/load_data.py")

with duckdb.connect(str(DB), read_only=True) as con:
    result = con.execute(path.read_text()).df()

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")
print(f"\n{path.name}: {len(result)} rows" + (f" (showing first {args.rows})" if len(result) > args.rows else ""))
print(result.head(args.rows).to_string(index=False))
