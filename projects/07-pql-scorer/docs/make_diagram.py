"""Writes docs/pql-scorer.excalidraw. Render it to PNG with any Excalidraw renderer."""
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


text(40, 20, "PQL scorer: score at first event + 30 minutes, using nothing later", 26, "#1e40af")
text(40, 58, "Real web-shop events (RetailRocket, 2015). Figures are from the committed run. A shop, not a B2B trial.", 16, "#6b7280")

box(40, 130, 180, 80, "Event feed\n2.76M rows", "#fed7aa", "#c2410c", "ellipse")
box(290, 130, 220, 80, "Tracking-plan\nvalidation")
box(580, 130, 220, 80, "Cohort:\nnew visitors only")
box(870, 130, 220, 80, "Features up to\nthe cut-off")
box(1160, 130, 220, 80, "Model +\nPlatt calibration")
for x1, x2 in ((220, 288), (510, 578), (800, 868), (1090, 1158)):
    arrow(x1, 170, x2, 170)

arrow(400, 210, 400, 278, "#b91c1c")
box(290, 280, 220, 80, "Quarantine and count\nover 1% bad: stop", "#fecaca", "#b91c1c")
arrow(690, 210, 690, 278, "#b91c1c")
box(560, 280, 260, 100, "Excluded: burn-in,\nlabel not yet known,\nbought already, bot-like", "#fecaca", "#b91c1c")
arrow(980, 210, 980, 278, "#b91c1c", True)
box(870, 280, 220, 80, "Later event seen?\nraise an error", "#fecaca", "#b91c1c")

arrow(1270, 210, 1270, 438)
box(1150, 440, 240, 90, "Above a threshold,\nand the daily cap\nnot yet full?", "#fef3c7", "#b45309")

arrow(1148, 460, 1022, 460)
text(1066, 437, "A", 16)
box(760, 430, 260, 60, "A assist: 38 per day\n13.5% went on to buy", "#a7f3d0", "#047857")
arrow(1148, 510, 1022, 545)
text(1066, 502, "B", 16)
box(760, 515, 260, 60, "B nudge: 380 per day\n1.9% went on to buy", "#a7f3d0", "#047857")
arrow(1270, 530, 1270, 598, "#374151")
text(1282, 552, "neither", 16)
box(1150, 600, 240, 60, "No extra action\n0.13% bought", "#e5e7eb", "#374151")

arrow(758, 460, 602, 495, "#1e3a5f")
arrow(758, 545, 602, 515, "#1e3a5f")
box(360, 465, 240, 80, "Randomise inside\nthe tier")
arrow(358, 485, 232, 460)
arrow(358, 525, 232, 555)
box(40, 430, 190, 60, "Treatment: act", "#a7f3d0", "#047857")
box(40, 525, 190, 60, "Holdout: do not act", "#e5e7eb", "#374151")

text(40, 625, "Only the treatment vs holdout difference shows that acting causes purchases.", 18, "#b91c1c")
text(40, 655, "A high buy rate in tier A is prediction. Those visitors might have bought anyway.", 16, "#374151")
text(40, 700, "Fit on first visits 17 May to 12 July. Choose model, calibrator and thresholds on 20 July to 7 August.\n"
     "Report on first visits from 15 August. 7-day gaps let each period's labels finish before the next starts.", 16, "#1e3a5f")

out = Path(__file__).with_name("pql-scorer.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out.name)
