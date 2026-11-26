"""Writes docs/churn_alert.excalidraw. Render it to PNG with any Excalidraw renderer."""
from __future__ import annotations

import json
from pathlib import Path

els: list[dict] = []


def base(kind: str, x: float, y: float, w: float, h: float, **kw: object) -> dict:
    n = len(els) + 1
    return {"id": f"e{n}", "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0, "strokeColor": "#1e3a5f",
            "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0,
            "opacity": 100, "groupIds": [], "frameId": None, "roundness": {"type": 3} if kind == "rectangle" else None,
            "seed": 1000 + n, "version": 1, "versionNonce": 2000 + n, "isDeleted": False, "boundElements": [], "updated": 1,
            "link": None, "locked": False, **kw}


def text(x: float, y: float, s: str, size: int = 16, color: str = "#374151", w: int | None = None, align: str = "left") -> None:
    lines = s.split("\n")
    w = w or int(max(len(line) for line in lines) * size * 0.6) + 4
    els.append(base("text", x, y, w, int(len(lines) * size * 1.25), strokeColor=color, text=s, originalText=s, fontSize=size,
                    fontFamily=3, textAlign=align, verticalAlign="top", containerId=None, lineHeight=1.25))


def box(x: float, y: float, w: float, h: float, label: str, fill: str = "#dbeafe", stroke: str = "#1e3a5f",
        kind: str = "rectangle") -> None:
    els.append(base(kind, x, y, w, h, backgroundColor=fill, strokeColor=stroke))
    text(x + 8, y + h / 2 - (label.count("\n") + 1) * 9.4, label, 15, "#111827", int(w - 16), "center")


def arrow(x1: float, y1: float, x2: float, y2: float, color: str = "#1e3a5f", dashed: bool = False) -> None:
    els.append(base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), strokeColor=color, points=[[0, 0], [x2 - x1, y2 - y1]],
                    strokeStyle="dashed" if dashed else "solid", startBinding=None, endBinding=None, startArrowhead=None,
                    endArrowhead="arrow", lastCommittedPoint=None))


text(40, 20, "Revenue retention and churn-risk alerts", 26, "#1e40af")
text(40, 58, "Real invoices from one UK gift-ware seller, 2009-2011. Not SaaS contract data.", 16, "#6b7280")

box(40, 150, 170, 80, "Invoice lines\n(two sheets)", "#fed7aa", "#c2410c", "ellipse")
box(280, 150, 220, 80, "SQLite: every row\ngets one bucket")
box(570, 135, 220, 110, "Balances to\nthe penny?", "#fef3c7", "#b45309", "diamond")
box(880, 150, 210, 80, "GRR, NRR,\nwaterfall, cohorts", "#a7f3d0", "#047857")
box(580, 300, 200, 60, "Stop the run", "#fecaca", "#b91c1c")
arrow(212, 190, 278, 190)
arrow(500, 190, 568, 190)
arrow(790, 190, 878, 190)
text(818, 166, "yes", 14)
arrow(680, 245, 680, 298, "#b91c1c")
text(692, 262, "no", 14)

text(40, 405, "At each scoring day t (point in time)", 20, "#1e40af")
box(40, 455, 250, 90, "Features\nrows before t only\n(180-day lookback)")
box(360, 455, 250, 90, "Train on past days s\nwhere s + 90 days <= t")
box(680, 455, 230, 90, "Score eligible\naccounts\n(2+ buys, recent)")
box(980, 455, 230, 90, "Rank by churn\nscore (default)")
arrow(292, 500, 358, 500)
arrow(612, 500, 678, 500)
arrow(912, 500, 978, 500)

box(980, 620, 230, 100, "Alerted in the\nlast 28 days?", "#fef3c7", "#b45309", "diamond")
box(680, 635, 230, 70, "Top 25 + reasons\n(local CSV)", "#a7f3d0", "#047857")
box(1290, 640, 150, 60, "Skip", "#e5e7eb", "#374151")
arrow(1095, 547, 1095, 618)
arrow(978, 670, 912, 670)
text(944, 638, "no", 14)
arrow(1212, 670, 1288, 670, "#374151")
text(1232, 646, "yes", 14)

box(360, 635, 250, 70, "Human: hold out a\nrandom share, then act", "#ede9fe", "#6d28d9")
box(40, 635, 250, 70, "Human: compare both\narms after 90 days", "#ede9fe", "#6d28d9")
arrow(678, 670, 612, 670, "#6d28d9", True)
arrow(358, 670, 292, 670, "#6d28d9", True)

BACKTEST = ("Backtest: the same steps replayed weekly. "
            "Development weeks choose the model; later test weeks only measure it.")
text(40, 750, BACKTEST, 16, "#1e3a5f")
HUMAN = ("Dashed arrows are the proposed human process. "
         "The code sends nothing and has not measured any outreach effect.")
text(40, 780, HUMAN, 16, "#6d28d9")

out = Path(__file__).with_name("churn_alert.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out.name)
