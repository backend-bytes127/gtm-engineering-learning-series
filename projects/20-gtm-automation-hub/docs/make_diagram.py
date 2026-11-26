"""Writes docs/signal-to-action-hub.excalidraw. Render it to PNG with any Excalidraw renderer."""
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


SOURCE = ("#fed7aa", "#c2410c")
CHECK = ("#fef3c7", "#b45309")
BAD = ("#fecaca", "#b91c1c")
GOOD = ("#a7f3d0", "#047857")

text(40, 20, "GTM signal-to-action hub: three local n8n workflows", 26, "#1e40af")
text(40, 58, "Synthetic payloads. Tested with a local fake in place of Slack. One production execution at a time.", 16, "#6b7280")

text(40, 110, "A. Weekly churn-risk digest", 20, "#1e40af")
box(40, 145, 220, 70, "Queue CSV\n(project 11 shape)", *SOURCE)
box(340, 145, 240, 70, "Every row valid?")
box(660, 145, 240, 70, "Build digest\n(top 5 + reasons)")
box(1220, 145, 220, 70, "Send, 3 tries", *GOOD)
arrow(260, 180, 338, 180)
arrow(580, 180, 658, 180)
arrow(900, 180, 1218, 180)
arrow(460, 215, 460, 258, BAD[1])
box(340, 260, 240, 56, "Fail: nothing sent", *BAD)
arrow(1330, 215, 1330, 258, BAD[1])
box(1220, 260, 220, 56, "All fail: run fails", *BAD)

text(40, 360, "B and C. Signed webhooks (B = PQL lead, C = inbound signal)", 20, "#1e40af")
box(40, 400, 220, 70, "Signed POST\nlead or signal", *SOURCE)
box(340, 400, 240, 70, "HMAC valid and\nunder 5 minutes?", *CHECK)
box(660, 400, 240, 70, "Signature not\nseen before?", *CHECK)
box(980, 400, 160, 70, "Contract\nvalid?", *CHECK)
box(1220, 400, 220, 70, "Event already\ndelivered?", *CHECK)
for x1, x2 in ((260, 338), (580, 658), (900, 978), (1140, 1218)):
    arrow(x1, 435, x2, 435)
arrow(460, 470, 460, 518, BAD[1])
box(340, 520, 240, 56, "401: nothing stored", *BAD)
arrow(780, 470, 780, 518, BAD[1])
box(660, 520, 240, 56, "409: replay", *BAD)
arrow(1060, 470, 1060, 518, BAD[1])
box(980, 520, 160, 56, "422: invalid", *BAD)
arrow(1060, 576, 1060, 718, BAD[1])
arrow(1330, 470, 1330, 518, "#374151")
text(1342, 484, "yes", 14)
box(1220, 520, 220, 56, "200: duplicate", "#e5e7eb", "#374151")
arrow(1440, 435, 1520, 435)
text(1462, 412, "no", 14)
box(1522, 400, 190, 70, "Send to Slack\n3 tries")
arrow(1712, 435, 1788, 435, GOOD[1])
box(1790, 400, 220, 70, "Mark as seen\n(B: pending)", *GOOD)
text(1722, 480, "accepted", 14, GOOD[1])
els.append(base("line", 1617, 470, 0, 290, strokeColor=BAD[1], points=[[0, 0], [0, 290]], strokeStyle="solid",
                startBinding=None, endBinding=None, startArrowhead=None, endArrowhead=None, lastCommittedPoint=None))
arrow(1617, 760, 1282, 760, BAD[1])
text(1380, 736, "all tries fail", 14, BAD[1])
box(900, 720, 380, 80, "Dead-letter list\n(a failed send is not marked seen,\nso a re-signed retry works)", *BAD)
text(40, 600, "B sends only tier A leads.\nOther tiers answer 200 not_routed.", 14, "#6b7280")

text(40, 850, "B continued: the human decision", 20, "#1e40af")
box(40, 890, 220, 80, "Approve or Dismiss\nclick", *SOURCE)
box(340, 890, 240, 80, "Slack signature,\n5 minutes, no replay", *CHECK)
box(660, 890, 240, 80, "Allowed user, and\nlead still pending?", *CHECK)
box(980, 890, 240, 80, "Record decision\nacknowledge", *GOOD)
box(1300, 890, 300, 80, "Replace the message, only\nif reply URL host is expected")
for x1, x2 in ((260, 338), (580, 658), (900, 978), (1220, 1298)):
    arrow(x1, 930, x2, 930)
arrow(780, 970, 780, 1018, BAD[1])
box(630, 1020, 300, 56, "Nothing changes", *BAD)
text(40, 1110, "Not connected: a real click needs a public HTTPS address, which this local setup does not have.\n"
     "Approving records a decision. It does not contact anyone.", 16, "#b91c1c")

out = Path(__file__).with_name("signal-to-action-hub.excalidraw")
out.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                           "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}, indent=1) + "\n")
print(out)
