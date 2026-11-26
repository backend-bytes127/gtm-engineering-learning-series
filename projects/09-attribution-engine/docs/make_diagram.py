"""Writes docs/attribution.excalidraw. Render it to PNG with any Excalidraw renderer."""
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


text(40, 20, "Attribution you can defend: split credit, show the spread, then test", 26, "#1e40af")
text(40, 58, "Attribution divides conversions that happened. Only the randomised test estimates what a channel caused.", 16, "#6b7280")

# Row 1: from raw events to credit
box(40, 130, 200, 90, "Raw events\nURL + referrer\nand conversions", "#fed7aa", "#c2410c")
box(290, 130, 200, 90, "Normalise channel\nunknown stays\n'unmapped'")
box(540, 130, 220, 90, "Point in time\nonly touches BEFORE\nthe conversion")
box(810, 130, 240, 90, "8 methods\n5 positional, Markov,\n2 Shapley games")
box(1100, 120, 220, 110, "Credit adds up\nexactly?", "#fef3c7", "#b45309", "diamond")
for x1, x2 in ((240, 288), (490, 538), (760, 808), (1050, 1098)):
    arrow(x1, 175, x2, 175)
arrow(1210, 230, 1210, 318)
text(1224, 262, "yes\n(no: stop)", 14)

# Row 2: decision, right to left
box(1100, 320, 220, 90, "Spread per channel\nlow to high credit\nand cost")
box(780, 320, 250, 90, "Rank test backlog\nspend in dispute,\ncan we reach the sample?")
box(480, 320, 240, 90, "Randomised holdout\nintention-to-treat\nwith an interval", "#a7f3d0", "#047857")
box(180, 310, 230, 110, "Interval clear\nof the rule?", "#fef3c7", "#b45309", "diamond")
for x1, x2 in ((1098, 1032), (778, 722), (478, 412)):
    arrow(x1, 365, x2, 365)
arrow(295, 420, 295, 488)
text(309, 440, "yes", 14)
box(180, 490, 230, 70, "Budget decision:\nkeep, cut or scale", "#a7f3d0", "#047857", "ellipse")
arrow(180, 365, 112, 365)
text(128, 340, "no", 14)
box(20, 335, 90, 60, "Say\n'unknown'", "#e5e7eb", "#374151")

# Verification lane
text(40, 610, "How the methods are checked (synthetic world only)", 20, "#1e40af")
box(40, 655, 290, 90, "Planted world\nhidden intent, known\nchannel effects", "#ede9fe", "#6d28d9")
box(450, 655, 330, 90, "Replay the same users with\nchannels off = causal truth", "#ede9fe", "#6d28d9")
box(900, 655, 420, 90, "Score each method against truth\nand against an equal split", "#ede9fe", "#6d28d9")
arrow(330, 700, 448, 700, "#6d28d9", True)
arrow(780, 700, 898, 700, "#6d28d9", True)
text(40, 765, "The attribution code receives events only. It never reads the planted effects.", 16, "#6d28d9")

out = Path(__file__).with_name("attribution.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out.name)
