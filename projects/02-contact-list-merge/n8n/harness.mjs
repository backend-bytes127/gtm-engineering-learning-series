// Runs the GENERATED Code-node source from the workflow JSON (exactly what n8n runs) on dumped sheet data.
// Usage: node harness.mjs <workflow.json> <sheets.json> <out-dir>
import { readFileSync, writeFileSync } from 'node:fs';

const [workflowPath, sheetsPath, outDir] = process.argv.slice(2);
const workflow = JSON.parse(readFileSync(workflowPath, 'utf8'));
const sheets = JSON.parse(readFileSync(sheetsPath, 'utf8'));

const run = (name, items) => {
  const node = workflow.nodes.find((n) => n.name === name);
  if (!node) throw new Error(`node not found: ${name}`);
  const fn = new Function('$input', '$', node.parameters.jsCode);
  const lookup = (n) => ({ all: () => (sheets[n] || []).map((json) => ({ json })) });
  return fn({ all: () => items }, lookup);
};

const mapped = run('1 Map Columns', []);
const cleaned = run('2 Clean & Remove Invalid', mapped);
const kept = cleaned.filter((i) => i.json.status === 'kept');
const removed = cleaned.filter((i) => i.json.status === 'removed').map((i) => i.json);
const standardized = run('3 Standardize (Rules tab)', kept);
const grouped = run('4 Remove Duplicates (group same person)', standardized);
const merged = run('5 Enrich & Merge', grouped);
const finalRows = run('6 Final Output', merged).map((i) => i.json);

writeFileSync(`${outDir}/js_final.json`, JSON.stringify(finalRows));
writeFileSync(`${outDir}/js_audit.json`, JSON.stringify({
  removed, links: grouped.filter((i) => i.json.type === 'link-decision').map((i) => i.json),
  flags: merged.map((i) => ({ who: i.json['Contact Person Name'], flags: i.json._flags })),
}));
process.stdout.write(`mapped=${mapped.length} removed=${removed.length} kept=${kept.length} people=${finalRows.length}\n`);
