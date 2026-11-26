// Gate for POST /webhook/gtm-hub-slack-actions. Python reference: pipeline.handle_interaction.
// Slack treats a non-200 reply as an error, so business refusals still answer 200.
const DECISIONS = { pql_approve: 'approved', pql_dismiss: 'dismissed' };

const decodeField = (text) => decodeURIComponent(text.replace(/\+/g, ' '));

function parseClick(body) {
  try {
    const pair = body.toString('utf8').split('&').find((part) => part.startsWith('payload='));
    const payload = JSON.parse(decodeField(pair.slice('payload='.length)));
    const action = payload.actions[0];
    const click = {
      key: action.value,
      decision: has(DECISIONS, action.action_id) ? DECISIONS[action.action_id] : null,
      userId: payload.user.id,
      responseUrl: payload.response_url === undefined ? '' : payload.response_url,
    };
    const strings = [click.key, click.userId, click.responseUrl].every((value) => typeof value === 'string');
    const valid = payload.type === 'block_actions' && click.decision && strings && /^[A-Za-z0-9]+$/.test(click.userId);
    return valid ? click : null;
  } catch (error) {
    return null;
  }
}

const passed = await gate(SLACK, $env.SLACK_SIGNING_SECRET, { getInputData: () => $input.all(), helpers: this.helpers });
if (passed.done) return passed.done;
const { state, now, body } = passed;
const click = parseClick(body);
if (!click) return dead(state, 200, 'unsupported_interaction', null, { sha256: sha256(body) }, now);
const approvers = ($env.SLACK_APPROVER_IDS || '').split(',').map((id) => id.trim()).filter(Boolean);
if (approvers.length && !approvers.includes(click.userId)) return answer(200, 'not_allowed');
if (!has(state.events, click.key)) return answer(200, 'unknown_lead');
if (state.events[click.key].status !== 'pending') return answer(200, 'already_decided');
writeState(recordEvent(state, click.key, { status: click.decision, by: click.userId }, now));

// The reply URL arrives inside the request. Only post to the expected host.
const prefix = $env.GTM_HUB_RESPONSE_URL_PREFIX || 'https://hooks.slack.com/';
const allowed = prefix.endsWith('/') && click.responseUrl.startsWith(prefix);
const text = `PQL \`${escapeMrkdwn(click.key)}\` ${click.decision} by <@${click.userId}>. Nothing was sent to the lead.`;
return answer(200, click.decision, {
  deliver: allowed,
  target: click.responseUrl,
  message: { replace_original: true, text, blocks: [section(text)] },
});
