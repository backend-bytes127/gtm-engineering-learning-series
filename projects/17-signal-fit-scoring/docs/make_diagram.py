"""Writes docs/signal-fit-scoring.excalidraw. Render it to PNG with any Excalidraw renderer."""
import json
from pathlib import Path

els, n = [], 0


def base(kind, x, y, w, h, **kw):
    global n
    n += 1
    return {"id": f"e{n}", "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0, "strokeColor": "#1e3a5f",
            "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0,
            "opacity": 100, "groupIds": [], "frameId": None, "roundness": {"type": 3} if kind == "rectangle" else None,
            "seed": 1000 + n, "version": 1, "versionNonce": 2000 + n, "isDeleted": False, "boundElements": [], "updated": 1,
            "link": None, "locked": False, **kw}


def text(x, y, s, size=16, color="#374151", w=None, align="left"):
    lines = s.split("\n")
    w = w or int(max(len(line) for line in lines) * size * 0.6) + 4
    els.append(base("text", x, y, w, int(len(lines) * size * 1.25), strokeColor=color, text=s, originalText=s, fontSize=size,
                    fontFamily=3, textAlign=align, verticalAlign="top", containerId=None, lineHeight=1.25))


def box(x, y, w, h, label, fill="#dbeafe", stroke="#1e3a5f", kind="rectangle"):
    els.append(base(kind, x, y, w, h, backgroundColor=fill, strokeColor=stroke))
    lines = label.count("\n") + 1
    text(x + 8, y + h / 2 - lines * 10, label, 16, "#111827", w - 16, "center")


def arrow(x1, y1, x2, y2, color="#1e3a5f", dashed=False):
    els.append(base("arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), strokeColor=color, points=[[0, 0], [x2 - x1, y2 - y1]],
                    strokeStyle="dashed" if dashed else "solid", startBinding=None, endBinding=None, startArrowhead=None,
                    endArrowhead="arrow", lastCommittedPoint=None))


def segment(x1, y1, x2, y2, color):
    els.append(base("line", x1, y1, abs(x2 - x1), abs(y2 - y1), strokeColor=color, points=[[0, 0], [x2 - x1, y2 - y1]],
                    strokeStyle="dashed", startBinding=None, endBinding=None, startArrowhead=None, endArrowhead=None,
                    lastCommittedPoint=None))


text(40, 20, "Who to work first: score only with what exists before the first call", 26, "#1e40af")
text(40, 58, "Real data: UCI Bank Marketing (CC BY 4.0). Consumer phone campaigns 2008-2010, not B2B pipeline.", 16, "#6b7280")

box(40, 130, 250, 110, "Allowed: job, education,\ncredit and loan flags,\nearlier campaigns", "#a7f3d0", "#047857")
box(40, 290, 250, 130, "Kept out: call length,\ncall count, call timing,\nage, marital status,\nmarket indicators", "#fecaca", "#b91c1c")
box(370, 150, 220, 70, "Point-in-time\nfeatures")
box(670, 150, 240, 70, "Walk forward: train\non earlier months only")
box(990, 150, 220, 70, "Score the\nnext month")
box(1290, 140, 230, 90, "Beats simple\nrules?", "#fef3c7", "#b45309", "diamond")
arrow(290, 185, 368, 185, "#047857")
arrow(590, 185, 668, 185)
arrow(910, 185, 988, 185)
arrow(1210, 185, 1288, 185)
arrow(290, 355, 368, 355, "#b91c1c", True)
box(370, 320, 220, 70, "Leakage ladder:\nwhat each would add", "#e5e7eb", "#374151")
box(670, 320, 240, 70, "Simple rules, scored\non the same months", "#e5e7eb", "#374151")
segment(910, 355, 1405, 355, "#374151")
arrow(1405, 355, 1405, 232, "#374151", True)

text(1000, 368, "judged with bootstrap intervals", 14, "#6b7280")
box(1640, 150, 260, 70, "No or unclear:\nthe rule stays the bar", "#e5e7eb", "#374151")
box(1640, 300, 260, 90, "Yes, clearly:\ntrial the model\nin shadow", "#a7f3d0", "#047857")
arrow(1520, 185, 1638, 185)
text(1566, 162, "no", 14)
arrow(1463, 208, 1638, 325, "#047857")
text(1556, 245, "yes", 14, "#047857")

text(40, 470, "The scoring command (new rows)", 20, "#1e40af")
box(40, 520, 210, 80, "New rows\n(CSV)", "#fed7aa", "#c2410c", "ellipse")
box(330, 525, 240, 70, "Validate; blank or\nunseen = neutral, listed")
box(650, 525, 240, 70, "JSON model: score\nand reason codes")
box(970, 525, 240, 70, "Rank inside\nthe batch")
arrow(250, 560, 328, 560)
arrow(570, 560, 648, 560)
arrow(890, 560, 968, 560)
box(1330, 470, 190, 60, "A: top 10%", "#a7f3d0", "#047857")
box(1330, 550, 190, 60, "B: next 20%", "#fef3c7", "#b45309")
box(1330, 630, 190, 60, "C: the rest", "#e5e7eb", "#374151")
arrow(1210, 560, 1328, 500)
arrow(1210, 560, 1328, 580)
arrow(1210, 560, 1328, 660)
box(1590, 630, 250, 60, "Random sample of\nB and C also worked")
arrow(1520, 660, 1588, 660)
arrow(1520, 580, 1588, 645)
segment(1715, 692, 1715, 750, "#047857")
segment(1715, 750, 790, 750, "#047857")
arrow(790, 750, 790, 597, "#047857", True)
text(890, 762, "proposed, not built: outcomes of every worked row go into next month's training data", 14, "#047857")

out = Path(__file__).with_name("signal-fit-scoring.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out)
