"""Build step for hosting (D-048): install DuckDB's httpfs extension into a folder
inside the project, so the running API can read Parquet from Cloudflare R2.

Usage: python scripts/install_duckdb_extensions.py [folder]   (default .duckdb_extensions)
The API finds it through DUCKDB_EXTENSION_DIRECTORY.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

folder = Path(sys.argv[1] if len(sys.argv) > 1 else ".duckdb_extensions").resolve()
folder.mkdir(parents=True, exist_ok=True)
with duckdb.connect() as duck:
    duck.execute(f"SET extension_directory = '{folder}'")
    duck.execute("INSTALL httpfs")
    duck.execute("LOAD httpfs")
print(f"httpfs installed in {folder}")
