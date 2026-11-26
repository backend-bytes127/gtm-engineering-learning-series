"""Writes docs/waterfall.excalidraw. Render it to PNG with any Excalidraw renderer."""
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


text(40, 20, "Enrichment waterfall: one contact, one provider at a time", 26, "#1e40af")
text(40, 58, "All providers, prices and contacts are synthetic", 16, "#6b7280")
box(40, 150, 140, 70, "Contact\nname + domain", "#fed7aa", "#c2410c", "ellipse")
box(260, 140, 200, 90, "Already in the\nledger?", "#fef3c7", "#b45309", "diamond")
box(540, 150, 200, 70, "Reserve full price\n(refuse if over cap)")
box(820, 150, 180, 70, "Call provider\n(retry if unbilled)")
box(1080, 140, 200, 90, "Valid e-mail?", "#fef3c7", "#b45309", "diamond")
box(1360, 150, 160, 70, "Accept\nand stop", "#a7f3d0", "#047857", "ellipse")
arrow(180, 185, 258, 185)
arrow(460, 185, 538, 185)
text(478, 162, "no", 14)
arrow(740, 185, 818, 185)
arrow(1000, 185, 1078, 185)
arrow(1280, 185, 1358, 185)
text(1296, 162, "yes", 14)
arrow(1180, 230, 1180, 300)
text(1192, 252, "no, catch-all\nor invalid", 14)
box(1080, 302, 200, 70, "Next provider\n(or give up)", "#e5e7eb", "#374151")
arrow(1078, 337, 362, 337, "#374151", True)
arrow(360, 337, 360, 232, "#374151", True)
text(372, 262, "ask the next\nprovider", 14)
for x1, y1, x2, y2 in ((360, 140, 360, 108), (360, 108, 1180, 108)):
    els.append(base("line", x1, y1, abs(x2 - x1), abs(y2 - y1), strokeColor="#047857", points=[[0, 0], [x2 - x1, y2 - y1]],
                    strokeStyle="dashed", startBinding=None, endBinding=None, startArrowhead=None, endArrowhead=None, lastCommittedPoint=None))
arrow(1180, 108, 1180, 138, "#047857", True)
text(560, 86, "yes: use the stored answer and pay nothing", 14, "#047857")

text(40, 430, "What each failure does to the money", 20, "#1e40af")
rows = [("Refused (429) or server error", "not billed: retry up to 3 times, then release the reservation", "#dbeafe"),
        ("Reply is unreadable", "assume billed: record it, never ask again", "#fef3c7"),
        ("No reply (timeout)", "billing unknown: count as spent, mark unknown, never retry", "#fecaca"),
        ("Run stops after a call", "reservation stays: counted as spent, not called again", "#fecaca")]
for i, (cause, effect, fill) in enumerate(rows):
    y = 475 + i * 62
    box(40, y, 320, 46, cause, fill)
    arrow(360, y + 23, 428, y + 23)
    text(440, y + 13, effect, 16)
text(40, 745, "Ledger key: (provider, normalised contact). It is the cache, the spend record and the retry guard.", 16, "#1e3a5f")

out = Path(__file__).with_name("waterfall.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out)
