"""Guards for the no-build front end. A broken ES-module import blanks the whole page, and only a browser notices."""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
JS_FILES = sorted((STATIC / "js").rglob("*.js"))
EXPORT = re.compile(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+(\w+)")
IMPORT = re.compile(r"import\s*(?:\*\s+as\s+\w+|\{([^}]*)\})\s*from\s*\"([^\"]+)\"")


def exports_of(path: Path) -> set[str]:
    return set(EXPORT.findall(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: str(p.relative_to(STATIC)))
def test_every_named_import_is_exported_by_its_module(path):
    for names, target in IMPORT.findall(path.read_text(encoding="utf-8")):
        module = (path.parent / target).resolve()
        assert module.is_file(), f"{path.name} imports {target}, which does not exist"
        wanted = {n.strip().split(" as ")[0] for n in names.split(",") if n.strip()}
        missing = wanted - exports_of(module)
        assert not missing, f"{path.name} imports {sorted(missing)} from {target}, which does not export them"


def test_every_page_in_the_router_exists_and_exports_render():
    app = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    pages = re.findall(r"from \"\./pages/(\w+)\.js\"", app)
    assert len(pages) == 8
    for name in pages:
        assert "render" in exports_of(STATIC / "js" / "pages" / f"{name}.js"), name


def test_the_front_end_never_writes_untrusted_text_as_html():
    """Contact names and companies come from an uploaded file. They must only ever reach the page as text."""
    for path in JS_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write", text), path.name


def test_index_loads_the_module_entry_and_the_stylesheet():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'src="/js/app.js"' in html and 'href="/app.css"' in html and "<title>" in html
