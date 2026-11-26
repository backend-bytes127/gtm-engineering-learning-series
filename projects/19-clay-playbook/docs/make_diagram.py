"""Writes docs/clay-playbook.excalidraw. Render it to PNG with any Excalidraw renderer."""

import json
from pathlib import Path

els: list[dict] = []


def base(kind: str, x: float, y: float, w: float, h: float, **kw) -> dict:
    n = len(els) + 1
    return {"id": f"e{n}", "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0, "strokeColor": "#1e3a5f",
            "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0,
            "opacity": 100, "groupIds": [], "frameId": None, "roundness": {"type": 3} if kind == "rectangle" else None,
            "seed": 1000 + n, "version": 1, "versionNonce": 2000 + n, "isDeleted": False, "boundElements": [], "updated": 1,
            "link": None, "locked": False, **kw}


def text(x: float, y: float, s: str, size: int = 16, color: str = "#374151", w: float | None = None, align: str = "left") -> None:
    lines = s.split("\n")
    w = w or int(max(len(line) for line in lines) * size * 0.6) + 4
    els.append(base("text", x, y, w, int(len(lines) * size * 1.25), strokeColor=color, text=s, originalText=s, fontSize=size,
                    fontFamily=3, textAlign=align, verticalAlign="top", containerId=None, lineHeight=1.25))


def box(x: float, y: float, w: float, h: float, label: str, fill: str = "#dbeafe", stroke: str = "#1e3a5f",
        kind: str = "rectangle") -> None:
    els.append(base(kind, x, y, w, h, backgroundColor=fill, strokeColor=stroke))
    lines = label.count("\n") + 1
    text(x + 8, y + h / 2 - lines * 10, label, 16, "#111827", w - 16, "center")


def arrow(x1: float, y1: float, x2: float, y2: float, color: str = "#1e3a5f") -> None:
    els.append(base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), strokeColor=color, points=[[0, 0], [x2 - x1, y2 - y1]],
                    startBinding=None, endBinding=None, startArrowhead=None, endArrowhead="arrow", lastCommittedPoint=None))


text(40, 20, "Clay playbook: score for free, then pay only where it can change a decision", 26, "#1e40af")
text(40, 58, "Counts from one run on 25 companies. No company-level data is shown.", 16, "#6b7280")

# Row 1: free work and the gate
box(40, 120, 250, 90, "Company search\nNL or DE, 51-500\nabout 126 match", "#fed7aa", "#c2410c")
box(350, 120, 220, 90, "Save 25 rows\nauto-run off")
box(630, 120, 280, 90, "Free formulas\nclean, vendor model,\nscore, reasons, tier")
box(970, 110, 230, 110, "Tier A or B?", "#fef3c7", "#b45309", "diamond")
box(1290, 130, 240, 70, "15 rows\nNOT_CHECKED", "#e5e7eb", "#374151")
arrow(290, 165, 348, 165)
arrow(570, 165, 628, 165)
arrow(910, 165, 968, 165)
arrow(1200, 165, 1288, 165, "#374151")
text(1222, 140, "no", 14)
arrow(1085, 220, 1085, 298)
text(1097, 246, "yes: 10 rows", 14)

# Row 2: two-step waterfall
box(945, 300, 280, 90, "Step 1: job openings\n(By Clay), 90 days\n4.0 credits")
box(560, 290, 230, 110, "Jobs found?", "#fef3c7", "#b45309", "diamond")
box(150, 300, 280, 90, "Step 2: PredictLeads\non the 2 misses\n1.0 credit, found 0")
arrow(945, 345, 792, 345)
arrow(560, 345, 432, 345)
text(466, 320, "no: 2", 14)
arrow(675, 400, 675, 498)
text(687, 436, "yes: 8", 14)

# Row 3: outcomes
box(560, 500, 230, 110, "Step 1 count\nover 100?", "#fef3c7", "#b45309", "diamond")
box(150, 520, 280, 70, "2 rows\nNO_JOBS_FOUND", "#e5e7eb", "#374151")
box(945, 465, 300, 70, "2 rows REVIEW_COUNT\ncheck whose domain it is", "#fecaca", "#b91c1c")
box(945, 575, 300, 70, "6 rows HIRING\ncheck job relevance", "#a7f3d0", "#047857")
arrow(290, 390, 290, 518, "#374151")
text(302, 440, "still nothing: 2", 14)
arrow(790, 555, 943, 502, "#b91c1c")
text(826, 498, "yes: 2", 14)
arrow(790, 555, 943, 608, "#047857")
text(832, 600, "no: 6", 14)

text(40, 760, "The Tier A or B pass rule rests on a keyword rule that has NOT been validated.", 18, "#b91c1c")
text(40, 690, "Total: 5.0 data credits and 10 actions. Both providers listed 0.5 per row;", 18, "#1e3a5f")
text(40, 718, "in this run step 1 did not bill its 2 misses, while step 2 did bill its 2 misses.", 18, "#1e3a5f")

out = Path(__file__).with_name("clay-playbook.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out)
