// Runs INSIDE the n8n container: prints the final rows of the latest Contact List Merge execution as JSON.
// n8n keeps execution data in SQLite, serialized with `flatted`. Both modules ship with n8n.
// A script file resolves modules relative to itself (/tmp), so anchor resolution at n8n's own install.
const n8nRequire = require('module').createRequire('/usr/local/lib/node_modules/n8n/package.json');
const sqlite3 = n8nRequire('sqlite3');
const flatted = n8nRequire('flatted');

const db = new sqlite3.Database('/home/node/.n8n/database.sqlite', sqlite3.OPEN_READONLY);
const sql = `select e.id, e.status, d.data from execution_entity e
             join execution_data d on d.executionId = e.id
             where e.workflowId = 'contactListMerge01' order by e.id desc limit 1`;
db.get(sql, (err, row) => {
  if (err || !row) { process.stdout.write(`${JSON.stringify({ status: 'none' })}\n`); return; }
  const runData = flatted.parse(row.data).resultData.runData;
  const finalNode = runData['6 Final Output'];
  const final = finalNode ? finalNode[0].data.main[0].map((item) => item.json) : [];
  process.stdout.write(`${JSON.stringify({ id: row.id, status: row.status, final })}\n`);
});
