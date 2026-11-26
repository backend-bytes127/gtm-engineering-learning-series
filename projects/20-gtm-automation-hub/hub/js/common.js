// Shared by every webhook gate. The generator pastes this above each node script.
// Python reference: hub/signing.py, hub/state.py, hub/pipeline.py.
const crypto = require('crypto');

const TOLERANCE_SECONDS = 300;
const MIN_SECRET_LENGTH = 16;
const MAX_BODY_BYTES = 16384;
const EVENT_RETENTION_SECONDS = 7 * 24 * 3600;
const MAX_EVENTS = 2000;
const MAX_DEAD_LETTERS = 100;
const GENERIC = { version: 'v1', ts: 'x-gtm-timestamp', sig: 'x-gtm-signature' };
const SLACK = { version: 'v0', ts: 'x-slack-request-timestamp', sig: 'x-slack-signature' };
const ID = /^[A-Za-z0-9_.:-]{1,80}$/;
const UTC = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/;

const sha256 = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');
const has = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const matches = (pattern, value) => typeof value === 'string' && pattern.test(value);
const isText = (value, limit) => typeof value === 'string' && value.trim().length > 0 && value.length <= limit;
const escapeMrkdwn = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const section = (text) => ({ type: 'section', text: { type: 'mrkdwn', text } });
const context = (text) => ({ type: 'context', elements: [{ type: 'mrkdwn', text }] });
const header = (text) => ({ type: 'header', text: { type: 'plain_text', text } });

// The whole hub state lives in one top-level key, replaced on every change so n8n notices and saves it.
const store = $getWorkflowStaticData('global');
const readState = () => store.hub || { signatures: {}, events: {}, deadLetters: [] };
const writeState = (state) => { store.hub = state; };

function rememberSignature(state, signature, timestamp, now) {
  const live = Object.entries(state.signatures).filter(([, expiry]) => expiry >= now);
  return { ...state, signatures: { ...Object.fromEntries(live), [signature]: timestamp + TOLERANCE_SECONDS } };
}

function recordEvent(state, key, record, now) {
  const live = Object.entries(state.events).filter(([k, v]) => k !== key && now - v.at <= EVENT_RETENTION_SECONDS);
  const kept = Object.fromEntries(live.slice(-(MAX_EVENTS - 1)));
  return { ...state, events: { ...kept, [key]: { ...record, at: Math.floor(now) } } };
}

function addDeadLetter(state, reason, key, detail, now) {
  const entry = { reason, key, detail, at: Math.floor(now) };
  return { ...state, deadLetters: [...state.deadLetters, entry].slice(-MAX_DEAD_LETTERS) };
}

const answer = (status, outcome, extra = {}) => [{ json: { status, reply: { outcome }, deliver: false, ...extra } }];

function verify(scheme, secret, headers, body, now) {
  if ((secret || '').length < MIN_SECRET_LENGTH) return 'not_configured';
  const timestamp = headers[scheme.ts] || '';
  const signature = headers[scheme.sig] || '';
  if (!timestamp || !signature) return 'missing_headers';
  if (!/^[0-9]{1,12}$/.test(timestamp)) return 'bad_timestamp';
  if (Math.abs(now - Number(timestamp)) > TOLERANCE_SECONDS) return 'stale_timestamp';
  const base = Buffer.concat([Buffer.from(`${scheme.version}:${timestamp}:`), body]);
  const expected = Buffer.from(`${scheme.version}=${crypto.createHmac('sha256', secret).update(base).digest('hex')}`);
  const given = Buffer.from(signature);
  return expected.length === given.length && crypto.timingSafeEqual(expected, given) ? 'ok' : 'bad_signature';
}

// Authentication first. A rejected request writes nothing, so strangers cannot fill the state.
async function gate(scheme, secret, node) {
  const item = node.getInputData()[0];
  const hasBody = Boolean(item.binary && item.binary.data);
  const body = hasBody ? await node.helpers.getBinaryDataBuffer(0, 'data') : Buffer.alloc(0);
  if (body.length > MAX_BODY_BYTES) return { done: answer(413, 'too_large') };
  const now = Date.now() / 1000;
  const headers = item.json.headers || {};
  const reason = verify(scheme, secret, headers, body, now);
  if (reason !== 'ok') return { done: answer(reason === 'not_configured' ? 503 : 401, reason) };
  const state = readState();
  const signature = headers[scheme.sig];
  if (has(state.signatures, signature) && state.signatures[signature] >= now) return { done: answer(409, 'replay') };
  const next = rememberSignature(state, signature, Number(headers[scheme.ts]), now);
  writeState(next);
  return { body, now, state: next };
}

function dead(state, status, reason, key, detail, now) {
  writeState(addDeadLetter(state, reason, key, detail, now));
  return answer(status, reason);
}

function parseJsonEvent(passed, validate) {
  const { body, state, now } = passed;
  const digest = sha256(body);
  let event;
  try {
    const text = body.toString('utf8');
    if (!Buffer.from(text, 'utf8').equals(body)) throw new Error('not utf-8');
    event = JSON.parse(text);
  } catch (error) {
    return { done: dead(state, 422, 'invalid_json', null, { sha256: digest }, now) };
  }
  const fields = validate(event);
  if (fields.length) return { done: dead(state, 422, 'invalid_schema', null, { sha256: digest, fields }, now) };
  return { event };
}

const failing = (checks) => Object.entries(checks).filter(([, ok]) => !ok).map(([name]) => name);
