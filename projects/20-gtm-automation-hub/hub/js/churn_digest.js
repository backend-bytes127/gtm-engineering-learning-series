// Build the weekly digest. Python reference: churn.py and messages.churn_digest.
// Any bad row throws, which fails the execution before anything is posted.
const COLUMNS = ['rank', 'customer_id', 'churn_score', 'net_180d_gbp', 'value_at_risk_gbp', 'primary_reason',
  'all_reasons', 'suggested_action', 'delivery_status'];
const TOP_ACCOUNTS = 5;
const STALE_AFTER_DAYS = 8;

const rows = $input.all().map((item) => item.json).filter((row) => Object.keys(row).length);
if (!rows.length) throw new Error('queue is empty');
if (Object.keys(rows[0]).join(',') !== COLUMNS.join(',')) throw new Error('unexpected columns');

const accounts = rows.map((row) => {
  const amount = String(row.value_at_risk_gbp);
  if (!/^[0-9]{1,6}$/.test(String(row.rank)) || !row.customer_id || !row.primary_reason) {
    throw new Error('rank, customer_id and primary_reason are required');
  }
  if (!/^[0-9]{1,12}(\.[0-9]+)?$/.test(amount)) throw new Error('value_at_risk_gbp must be a plain number, zero or more');
  return {
    rank: Number(row.rank),
    id: String(row.customer_id),
    pence: Math.floor(Number(amount) * 100 + 0.5),
    reason: String(row.primary_reason),
    action: String(row.suggested_action || ''),
  };
}).sort((a, b) => a.rank - b.rank);

const escapeMrkdwn = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const pounds = (pence) => `£${String(Math.floor((pence + 50) / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`;
const section = (text) => ({ type: 'section', text: { type: 'mrkdwn', text } });
const context = (text) => ({ type: 'context', elements: [{ type: 'mrkdwn', text }] });

const groups = accounts.reduce((totals, account) => {
  const previous = totals.get(account.reason) || { count: 0, pence: 0 };
  return new Map(totals).set(account.reason, { count: previous.count + 1, pence: previous.pence + account.pence });
}, new Map());
const reasons = [...groups]
  .sort(([a, x], [b, y]) => y.count - x.count || (a < b ? -1 : 1))
  .map(([name, g]) => `• ${escapeMrkdwn(name)}: ${g.count} (${pounds(g.pence)})`)
  .join('\n');
const top = accounts.slice(0, TOP_ACCOUNTS)
  .map((a) => `${a.rank}. \`${escapeMrkdwn(a.id)}\` ${escapeMrkdwn(a.reason)}, ${pounds(a.pence)}: ${escapeMrkdwn(a.action)}`)
  .join('\n');

const { asOf } = $('Pick latest queue').first().json;
const total = accounts.reduce((sum, account) => sum + account.pence, 0);
const summary = `Churn-risk queue as of ${asOf}: ${accounts.length} accounts, ${pounds(total)} score-weighted trailing revenue`;
const blocks = [
  { type: 'header', text: { type: 'plain_text', text: 'Weekly churn-risk digest' } },
  section(summary),
  section(`*By primary reason*\n${reasons}`),
  section(`*Top ${Math.min(TOP_ACCOUNTS, accounts.length)} to review*\n${top}`),
  context('A ranking aid, not a forecast of lost money. Reasons describe behaviour; they do not prove a cause.'),
];
const today = new Date().toISOString().slice(0, 10);
const age = Math.round((Date.parse(today) - Date.parse(asOf)) / 86400000);
const stale = context(`:warning: This queue is ${age} days old. Check that the scoring job ran.`);
return [{ json: { message: { text: summary, blocks: age > STALE_AFTER_DAYS ? [...blocks, stale] : blocks } } }];
