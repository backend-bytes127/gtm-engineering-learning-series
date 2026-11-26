// Slack accepted the message: only now is the event recorded as seen.
const gated = $('Gate').first().json;
writeState(recordEvent(readState(), gated.key, gated.record, Date.now() / 1000));
return answer(200, gated.record.status);
