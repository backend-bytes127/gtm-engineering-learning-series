"""Build the visual build guide from guide.template.html.

    python3 build_guide.py                 # writes index.html (relative image paths, open locally or via GitHub Pages)
    python3 build_guide.py standalone.html # also writes one self-contained file with images embedded as data: URIs
"""
from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKELETON = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
            "{body}\n</body>\n</html>\n")


def embed_images(html: str, assets: Path) -> str:
    def repl(match: re.Match) -> str:
        path = assets / match.group(1)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f'src="data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"'

    return re.sub(r'src="assets/([^"]+)"', repl, html)


def main(standalone_out: str | None) -> None:
    template = (HERE / "guide.template.html").read_text()
    (HERE / "index.html").write_text(SKELETON.format(body=template))
    print(f"wrote {HERE / 'index.html'}")
    if standalone_out:
        out = Path(standalone_out)
        out.write_text(SKELETON.format(body=embed_images(template, HERE / "assets")))
        print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
