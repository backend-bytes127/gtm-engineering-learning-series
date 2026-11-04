"""Generate the n8n workflow JSON for the Contact List Merge from the sources in n8n/src/.

n8n Code nodes cannot import local modules, so each node's jsCode is assembled by concatenating the shared
helper modules it needs with its own step file. src/ is the single source of truth; the JSON is a build artifact.

    python3 n8n/build_workflow.py                       # standalone workflow  -> workflow/contact-list-merge.workflow.json
    python3 n8n/build_workflow.py --mode combined \\
        --base ../01-linkedin-icp-scraper/workflow/linkedin-icp-scraper.workflow.json \\
        --out /tmp/combined.json                         # Task 1 flow + this flow on one canvas
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
DEFAULT_OUT = HERE.parent / "workflow" / "contact-list-merge.workflow.json"
WORKFLOW_ID = "contactListMerge01"
FORM_PATH_ID = "contact-merge-form-0001"

FILES = (  # (node name, form field label, binary property, sheet, range to skip title rows)
    ("Extract Google Ads", "Google Ads", "Google_Ads", "leads", None),
    ("Extract Event Delegates", "Event", "Event", "Delegate List", "4"),  # numeric = skip 4 rows; "A5" reads one cell
    ("Extract Event Scans", "Event", "Event", "Booth Scans", None),
    ("Extract LinkedIn Form", "LinkedIn Form", "LinkedIn_Form", "leads", None),
    ("Extract Scraped LinkedIn", "Scraped LinkedIn", "Scraped_LinkedIn", "result", None),
    ("Extract Apollo", "Apollo", "Apollo", "apollo-contacts-export", None),
    ("Extract ZoomInfo", "ZoomInfo", "ZoomInfo", "ZoomInfo Contacts", None),
)
FORM_LABELS = ("Google Ads", "Event", "LinkedIn Form", "Scraped LinkedIn", "Apollo", "ZoomInfo")
FORM_HINTS = {
    "Google Ads": "01_GoogleAds_LeadForm_Export.xlsx", "Event": "02_Event_Delegates_and_Scans.xlsx",
    "LinkedIn Form": "03_LinkedIn_LeadGenForm_Export.xlsx", "Scraped LinkedIn": "04_LinkedIn_Scraped_SalesNav.xlsx",
    "Apollo": "05_ThirdParty_Apollo_Export.xlsx", "ZoomInfo": "06_ThirdParty_ZoomInfo_Export.xlsx",
}
# (node name, step file, shared modules in dependency order)
STEPS = (
    ("1 Map Columns", "n1_map.js", ("constants.js", "core.js")),
    ("2 Clean & Remove Invalid", "n2_clean.js", ("constants.js", "core.js")),
    ("3 Standardize (Rules tab)", "n3_standardize.js", ("constants.js", "core.js", "company.js")),
    ("4 Remove Duplicates (group same person)", "n4_group.js", ("constants.js", "core.js", "cluster.js")),
    ("5 Enrich & Merge", "n5_merge.js", ("constants.js", "core.js", "company.js", "merge.js")),
    ("6 Final Output", "n6_output.js", ("merge.js",)),
)
MERGE, KEEP, REMOVED, AUDIT, XLSX = ("Wait for all 7 sheets", "Kept or removed?", "Removed Records (log)",
                                      "Audit: Merge Log & Review Flags", "Convert to Final_Contact_List.xlsx")


def js(step_file: str, modules: tuple[str, ...]) -> str:
    return "\n".join([(SRC / m).read_text() for m in modules] + [(SRC / step_file).read_text()])


def node(name: str, ntype: str, version: float, params: dict, position: list[int], **extra: object) -> dict:
    node_id = "cm-" + hashlib.md5(name.encode()).hexdigest()[:8]  # stable across rebuilds (hash() is salted per run)
    return {"parameters": params, "id": node_id, "name": name, "type": ntype, "typeVersion": version,
            "position": position, **extra}


def build_nodes(y0: int) -> list[dict]:
    def pos(col: int, row: int = 0) -> list[int]:
        return [col * 280, y0 + row * 150]

    form = node("Contact Merge Form", "n8n-nodes-base.formTrigger", 2.2, {
        "formTitle": "Contact List Merge",
        "formDescription": "Upload the 6 source exports. You get back ONE cleaned, de-duplicated contact list (xlsx).",
        "path": "contact-merge",
        "formFields": {"values": [{"fieldLabel": lbl, "fieldType": "file", "multipleFiles": False,
                                   "acceptFileTypes": ".xlsx", "requiredField": True, "fieldName": lbl,
                                   "placeholder": FORM_HINTS[lbl]} for lbl in FORM_LABELS]},
        "options": {"formSubmittedText": "Received. The merge is running: open this workflow's Executions list and "
                                         "download Final_Contact_List.xlsx from the 'Convert to Final_Contact_List.xlsx' node."},
    }, pos(0, 3), webhookId=FORM_PATH_ID)
    extracts = [
        node(name, "n8n-nodes-base.extractFromFile", 1.1, {
            "operation": "xlsx", "binaryPropertyName": prop,
            "options": {"sheetName": sheet, "headerRow": True, **({"range": rng} if rng else {})}}, pos(1, i))
        for i, (name, _, prop, sheet, rng) in enumerate(FILES)
    ]
    merge = node(MERGE, "n8n-nodes-base.merge", 3, {"numberInputs": 7}, pos(2, 3))
    steps = [node(name, "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "jsCode": js(body, mods)},
                  pos(3 + i if i < 2 else 4 + i, 3)) for i, (name, body, mods) in enumerate(STEPS)]
    keep = node(KEEP, "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                       "conditions": [{"id": "kept-check", "leftValue": "={{ $json.status }}", "rightValue": "kept",
                                       "operator": {"type": "string", "operation": "equals"}}],
                       "combinator": "and"}, "options": {}}, pos(5, 3))
    removed = node(REMOVED, "n8n-nodes-base.noOp", 1, {}, pos(6, 5))
    audit = node(AUDIT, "n8n-nodes-base.noOp", 1, {}, pos(9, 5))
    to_xlsx = node(XLSX, "n8n-nodes-base.convertToFile", 1.1, {
        "operation": "xlsx", "binaryPropertyName": "data",
        "options": {"fileName": "Final_Contact_List.xlsx", "sheetName": "Final Output"}}, pos(11, 3))
    note = node("Note: Contact List Merge", "n8n-nodes-base.stickyNote", 1, {
        "width": 3400, "height": 760, "color": 5,
        "content": "## Contact List Merge\nUpload the 6 exports in the form. Steps 1-6 follow the task note: map columns, "
                   "clean + remove invalid, standardize (Rules tab), remove duplicates, enrich + merge, final output. "
                   "Click a Code node to see its data. Removed rows: 'Removed Records (log)'. Merge log and review "
                   "flags: 'Audit' node."}, [-40, y0 - 120])
    return [note, form, *extracts, merge, *steps, keep, removed, audit, to_xlsx]


def build_connections() -> dict:
    def link(target: str, index: int = 0) -> dict:
        return {"node": target, "type": "main", "index": index}

    names = [s[0] for s in STEPS]
    conns: dict[str, dict] = {"Contact Merge Form": {"main": [[link(f[0]) for f in FILES]]}}
    conns.update({f[0]: {"main": [[link(MERGE, i)]]} for i, f in enumerate(FILES)})
    conns[MERGE] = {"main": [[link(names[0])]]}
    conns[names[0]] = {"main": [[link(names[1])]]}
    conns[names[1]] = {"main": [[link(KEEP)]]}
    conns[KEEP] = {"main": [[link(names[2])], [link(REMOVED)]]}  # output 0 = kept, output 1 = removed
    conns[names[2]] = {"main": [[link(names[3])]]}
    conns[names[3]] = {"main": [[link(names[4])]]}
    conns[names[4]] = {"main": [[link(names[5]), link(AUDIT)]]}
    conns[names[5]] = {"main": [[link(XLSX)]]}
    return conns


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("standalone", "combined"), default="standalone")
    parser.add_argument("--base", type=Path, help="workflow JSON to append to (combined mode)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.mode == "standalone":
        wf = {"id": WORKFLOW_ID, "name": "Contact List Merge", "nodes": build_nodes(0),
              "connections": build_connections(), "settings": {"executionOrder": "v1"}}
    else:
        if not args.base:
            parser.error("--base is required in combined mode")
        raw = json.loads(args.base.read_text())
        base = raw[0] if isinstance(raw, list) else raw
        new_nodes = build_nodes(640)  # sits below the existing flow (which spans y=0..220)
        clash = {n["name"] for n in base["nodes"]} & {n["name"] for n in new_nodes}
        if clash:
            parser.error(f"node name clash: {sorted(clash)}")
        wf = {**base, "nodes": [*base["nodes"], *new_nodes], "connections": {**base["connections"], **build_connections()}}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out} ({len(wf['nodes'])} nodes, mode={args.mode})")


if __name__ == "__main__":
    main()
