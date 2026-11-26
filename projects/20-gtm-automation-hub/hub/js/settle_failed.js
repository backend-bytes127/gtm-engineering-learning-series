// All tries failed. Keep the authenticated event for repair; do not mark it seen, so a re-signed retry works.
// The HTTP error object is deliberately not copied: it can contain the Slack webhook URL.
const gated = $('Gate').first().json;
return dead(readState(), 502, 'delivery_failed', gated.key, { event: gated.event }, Date.now() / 1000);
