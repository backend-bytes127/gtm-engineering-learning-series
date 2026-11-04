// ---- core text helpers + LinkedIn + email + phone (port of pipeline/normalize.py) ----
const isBlank = (v) => v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v)) || String(v).trim() === '';
const s = (v) => (isBlank(v) ? '' : String(v).trim());
// -: n8n's xlsx reader (SheetJS) decodes 4-byte emoji such as U+1F680 into U+F680 (private use).
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}‍️-]+/gu;
const stripEmoji = (t) => t.replace(EMOJI, '');
const trimDots = (t) => t.replace(/^\.+|\.+$/g, '');
const capToken = (tok) => tok.split("'").map((p) => p.slice(0, 1).toUpperCase() + p.slice(1).toLowerCase()).join("'");

function cleanName(raw) {
  if (isBlank(raw)) return '';
  const text = stripEmoji(String(raw)).replace(/\([^)]*\)/g, ' ');
  let parts = text.split(',').map((p) => p.trim()).filter(Boolean);
  parts = parts.filter((p) => !CREDENTIALS.has(trimDots(p.toLowerCase())));
  if (parts.length === 2) parts = [parts[1], parts[0]];
  let tokens = parts.join(' ').split(/\s+/).filter(Boolean);
  while (tokens.length > 1 && SALUTATIONS.has(trimDots(tokens[0].toLowerCase()))) tokens = tokens.slice(1);
  return tokens.map(capToken).join(' ');
}
const letters = (t) => t.toLowerCase().replace(/[^a-z]/g, '');
const aliasFirst = (first) => FIRST_NAME_ALIASES[first.toLowerCase()] || first.toLowerCase();
const nameKey = (first, last) => `${first ? aliasFirst(first.split(/\s+/)[0]) : ''}|${letters(last)}`;
function slugToName(slug) {
  const base = slug.toLowerCase().replace(/-[0-9a-f]{8}$/, '').replace(/\d+$/, '');
  return base.replace(/-/g, ' ').trim();
}

// ---- LinkedIn ----
function linkedinSlug(raw) {
  if (isBlank(raw)) return '';
  const m = String(raw).trim().match(/linkedin\.com\/in\/([^/?#,\s]+)/i);
  if (!m) return '';
  const slug = m[1].toLowerCase();
  return slug.startsWith('acwa') ? '' : slug;
}
function linkedinAcwaa(raw) {
  const m = String(raw || '').match(/\/in\/(ACwA[^/?#,\s]+)|\/lead\/(ACwA[^,/?#\s]+)/);
  return m ? (m[1] || m[2]).toLowerCase() : '';
}
const linkedinUrl = (slug) => (slug ? `https://www.linkedin.com/in/${slug}` : '');

// ---- email ----
const domainOk = (d) => /^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/.test(d);
function splitEmails(raw) {
  if (isBlank(raw)) return [];
  const text = String(raw).toLowerCase().replace(/mailto:/g, '');
  return text.split(/[;,\s]+(?=\S+@)|;/)
    .map((p) => p.replace(/\s+/g, '').replace(/@@/g, '@'))
    .filter(Boolean);
}
function classifyEmail(email, knownDomains) {
  if (PLACEHOLDER_EMAILS.has(email) || email.split('@').length !== 2) return ['invalid', ''];
  const [local, domain] = email.split('@');
  if (TEST_EMAIL_DOMAINS.has(domain) || INVALID_EMAIL_DOMAIN_SUFFIXES.some((x) => domain.endsWith(x))) return ['invalid', ''];
  if (GENERIC_MAILBOXES.has(local)) return ['generic', ''];
  if (knownDomains.has(domain)) return ['ok', email];
  const candidates = [domain.replace(/\.con$/, '.com'), ...[...knownDomains].filter((d) => d.startsWith(`${domain}.`))];
  for (const cand of candidates) {
    if (cand !== domain && knownDomains.has(cand)) return ['repaired', `${local}@${cand}`];
  }
  return domainOk(domain) ? ['ok', email] : ['invalid', ''];
}
const isPersonalDomain = (email) => PERSONAL_EMAIL_DOMAINS.has(email.split('@').pop());

// ---- phone ----
const PHONE_RULES = [
  ['IN', /^\+91[6-9]\d{9}$/, '91', 12], ['US', /^\+1\d{10}$/, '1', 11], ['GB', /^\+447\d{9}$/, '44', 12],
  ['AE', /^\+9715\d{8}$/, '971', 12], ['SG', /^\+65[89]\d{7}$/, '65', 10],
];
const allFake = (d) => new Set(d).size === 1 || ['1234567890', '0123456789', '9876543210'].includes(d);
const validE164 = (e) => PHONE_RULES.some((r) => r[1].test(e));
function nationalToE164(digits, iso) {
  for (const [ruleIso, , prefix, length] of PHONE_RULES) {
    if (digits.length === length && digits.startsWith(prefix) && ruleIso !== 'US') return `+${digits}`;
  }
  if (digits.length === 11 && digits.startsWith('1') && iso === 'US') return `+${digits}`;
  if (iso === 'IN') {
    const d = digits.length === 11 && digits.startsWith('0') ? digits.slice(1) : digits;
    return d.length === 10 ? `+91${d}` : '';
  }
  if (iso === 'US') return digits.length === 10 ? `+1${digits}` : '';
  if (iso === 'SG') return digits.length === 8 ? `+65${digits}` : '';
  if (iso === 'AE') {
    const d = digits.startsWith('0') ? digits.slice(1) : digits;
    return d.length === 9 ? `+971${d}` : '';
  }
  return '';
}
function parseMobile(raw, country) {
  if (isBlank(raw)) return [null, 'empty'];
  let text = String(raw).trim().replace(/^'+/, '');
  if (PLACEHOLDER_PHONES.has(text.toLowerCase())) return [null, 'placeholder'];
  if (/^\d\.\d+E\+\d+$/i.test(text)) return [null, 'scientific-notation (digits lost)'];
  if (/^\d+\.0$/.test(text)) text = text.slice(0, -2);
  if (/^0\d{2,4}-\d{6,8}$/.test(text)) return [null, 'landline (STD code)'];
  text = text.replace(/\([^)\d]*[A-Za-z][^)]*\)/g, '');
  const digits = text.replace(/\D/g, '');
  if (!digits || allFake(digits.slice(-10))) return [null, 'fake/placeholder number'];
  let cand;
  if (text.startsWith('+')) cand = `+${digits}`;
  else if (digits.startsWith('00')) cand = `+${digits.slice(2)}`;
  else cand = nationalToE164(digits, COUNTRY_ISO[country] || '');
  return cand && validE164(cand) ? [cand, 'ok'] : [null, `unrecognised format (${text})`];
}
const phoneFromNotes = (notes) => {
  const m = String(notes || '').match(/Mob\s+(\d{7,12})/);
  return m ? m[1] : '';
};
