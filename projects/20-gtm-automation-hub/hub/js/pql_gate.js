// Gate for POST /webhook/gtm-hub-pql. Python reference: pipeline.handle_pql.
const TIERS = ['A_assist', 'B_nudge', 'C_none'];
const ALERT_TIER = 'A_assist';

function pqlErrors(event) {
  if (!isObject(event)) return ['not_an_object'];
  const key = event.idempotency_key;
  return failing({
    visitor_key: matches(ID, event.visitor_key),
    score_version: matches(ID, event.score_version),
    idempotency_key: matches(ID, key) && key === `${event.visitor_key}:${event.score_version}`,
    tier: TIERS.includes(event.tier),
    action: isText(event.action, 200),
    score: typeof event.score === 'number' && Number.isFinite(event.score) && event.score >= 0 && event.score <= 1,
    decided_at: matches(UTC, event.decided_at),
  });
}

const threeDecimals = (value) => (Math.round(value * 1000) / 1000).toFixed(3);
const button = (label, actionId, value, style) => (
  { type: 'button', text: { type: 'plain_text', text: label }, action_id: actionId, value, style }
);

function pqlMessage(event) {
  const summary = `PQL for review: ${escapeMrkdwn(event.visitor_key)} (tier ${event.tier})`;
  const detail = `*Account key:* \`${escapeMrkdwn(event.visitor_key)}\`\n`
    + `*Score:* ${threeDecimals(event.score)} (${escapeMrkdwn(event.score_version)})\n`
    + `*Suggested action:* ${escapeMrkdwn(event.action)}\n*Decided at:* ${event.decided_at}`;
  const key = event.idempotency_key;
  return {
    text: summary,
    blocks: [
      header('Product-qualified lead: needs a human'),
      section(detail),
      { type: 'actions', elements: [button('Approve', 'pql_approve', key, 'primary'), button('Dismiss', 'pql_dismiss', key, 'danger')] },
      context('Approving records a decision only. Nothing is sent to the lead.'),
    ],
  };
}

const passed = await gate(GENERIC, $env.GTM_HUB_WEBHOOK_SECRET, { getInputData: () => $input.all(), helpers: this.helpers });
if (passed.done) return passed.done;
const parsed = parseJsonEvent(passed, pqlErrors);
if (parsed.done) return parsed.done;
const { event } = parsed;
if (event.tier !== ALERT_TIER) return answer(200, 'not_routed');
if (has(passed.state.events, event.idempotency_key)) return answer(200, 'duplicate');
return [{ json: { deliver: true, key: event.idempotency_key, event, record: { status: 'pending' }, message: pqlMessage(event) } }];
