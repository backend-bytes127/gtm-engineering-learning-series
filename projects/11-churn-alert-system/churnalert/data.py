"""Load the two-sheet workbook into one validated line-level frame. Money is held as integer pence."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_COLUMNS = ["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
RAW_COLUMNS = ["sheet_no", "invoice", "stock_code", "qty", "ts", "pence", "customer_id", "country"]


def normalise(sheets: list[pd.DataFrame]) -> pd.DataFrame:
    """Rename, type and validate the source sheets. No row is dropped here: the SQL layer buckets them."""
    parts = []
    for number, sheet in enumerate(sheets, start=1):
        missing = [c for c in SOURCE_COLUMNS if c not in sheet.columns]
        if missing:
            raise ValueError(f"sheet {number} lacks columns: {missing}")
        required = sheet[["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price"]]
        if required.isna().any().any():
            raise ValueError(f"sheet {number} has empty invoice, stock code, quantity, date or price")
        parts.append(pd.DataFrame({
            "sheet_no": number,
            "invoice": sheet["Invoice"].astype(str).str.strip(),
            "stock_code": sheet["StockCode"].astype(str).str.strip().str.upper(),
            "qty": sheet["Quantity"].astype("int64"),
            "ts": pd.to_datetime(sheet["InvoiceDate"]),
            "pence": np.round(sheet["Quantity"].to_numpy(float) * sheet["Price"].to_numpy(float) * 100).astype("int64"),
            "customer_id": pd.to_numeric(sheet["Customer ID"]).astype("Int64"),
            "country": sheet["Country"].astype(str),
        }))
    return pd.concat(parts, ignore_index=True)[RAW_COLUMNS]


def load(xlsx: Path, cache: Path | None = None) -> pd.DataFrame:
    """Read the workbook (slow), caching the typed frame as parquet next to the raw file."""
    if not xlsx.exists():
        raise FileNotFoundError(f"{xlsx.name} not found: run `python fetch_data.py` first")
    if cache is not None and cache.exists() and cache.stat().st_mtime >= xlsx.stat().st_mtime:
        return pd.read_parquet(cache)
    frame = normalise(list(pd.read_excel(xlsx, sheet_name=None, engine="openpyxl").values()))
    if cache is not None:
        frame.to_parquet(cache, index=False)
    return frame
