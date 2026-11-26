// Gate for POST /webhook/gtm-hub-signal. Python reference: pipeline.handle_signal.
const TYPES = ['pricing_page_visit', 'demo_request', 'job_change', 'funding_news'];
const DOMAIN = /^(?=.{4,100}$)([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}$/;

function signalErrors(event) {
  if (!isObject(event)) return ['not_an_object'];
  return failing({
    event_id: matches(ID, event.event_id),
    type: TYPES.includes(event.type),
    account_domain: matches(DOMAIN, event.account_domain),
    occurred_at: matches(UTC, event.occurred_at),
    source: isText(event.source, 40),
  });
}

function signalMessage(event) {
  const summary = `New signal: ${event.type} at ${escapeMrkdwn(event.account_domain)}`;
  const detail = `*${summary}*\n*Source:* ${escapeMrkdwn(event.source)}\n*Occurred at:* ${event.occurred_at}`;
  return { text: summary, blocks: [section(detail), context(`Event \`${escapeMrkdwn(event.event_id)}\``)] };
}

const passed = await gate(GENERIC, $env.GTM_HUB_WEBHOOK_SECRET, { getInputData: () => $input.all(), helpers: this.helpers });
if (passed.done) return passed.done;
const parsed = parseJsonEvent(passed, signalErrors);
if (parsed.done) return parsed.done;
const { event } = parsed;
if (has(passed.state.events, event.event_id)) return answer(200, 'duplicate');
return [{ json: { deliver: true, key: event.event_id, event, record: { status: 'delivered' }, message: signalMessage(event) } }];
