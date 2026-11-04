"""Tidy an executed notebook so it diffs cleanly and opens with any Python 3 kernel.

Executing with a named kernel (for example a venv's) rewrites the kernelspec; this restores the portable
`python3` name and drops environment noise (font-cache messages, execution timing metadata).
"""
from __future__ import annotations

from pathlib import Path

import nbformat

PATH = Path(__file__).resolve().parent / "walkthrough.ipynb"
NOISE = ("font cache",)

nb = nbformat.read(PATH, as_version=4)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata["language_info"] = {"name": "python"}
for cell in nb.cells:
    cell.metadata.pop("execution", None)
    if cell.cell_type == "code":
        cell.outputs = [o for o in cell.outputs
                        if not (o.output_type == "stream" and any(n in "".join(o.text) for n in NOISE))]
nbformat.write(nb, PATH)
print(f"tidied {PATH.name}: {len(nb.cells)} cells")
