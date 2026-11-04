// ---- titles, company, location (port of pipeline/normalize.py) ----
const titleCase = (t) => t.replace(/[a-z]+/g, (w) => w[0].toUpperCase() + w.slice(1));

function canonicalTitle(raw) {
  if (isBlank(raw)) return '';
  const text = stripEmoji(String(raw)).split('|')[0].toLowerCase().replace(/\./g, '');
  const tokens = [];
  for (const tok of text.match(/[a-z]+/g) || []) {
    if (TITLE_DROP_TOKENS.has(tok)) continue;
    tokens.push(...(TOKEN_EXPANSIONS[tok] || [tok]));
  }
  if (!tokens.length) return '';
  if (tokens.includes('chief')) {
    const func = tokens.find((t) => ['executive', 'technology', 'revenue', 'marketing', 'operating', 'financial'].includes(t)) || '';
    return `Chief ${titleCase(func)} Officer`.replace(/ {2}/g, ' ');
  }
  const levels = new Set(['vice', 'president', 'director', 'head', 'manager', 'senior', 'lead']);
  const func = titleCase(tokens.filter((t) => !levels.has(t)).join(' '));
  if (tokens.includes('vice')) return `Vice President of ${func}`.trim();
  if (tokens.includes('director')) return `Director of ${func}`.trim();
  if (tokens.includes('head')) return `Head of ${func}`.trim();
  if (tokens.includes('manager')) return `${tokens.includes('senior') ? 'Senior ' : ''}${func} Manager`.replace(/ {2}/g, ' ').trim();
  if (tokens.includes('lead')) return `${func} Lead`.trim();
  return titleCase(tokens.join(' '));
}

// ---- difflib.SequenceMatcher.ratio() (no junk heuristics: strings are short) ----
function matchingBlocks(a, b) {
  const b2j = new Map();
  [...b].forEach((ch, j) => { if (!b2j.has(ch)) b2j.set(ch, []); b2j.get(ch).push(j); });
  const longest = (alo, ahi, blo, bhi) => {
    let besti = alo; let bestj = blo; let bestsize = 0; let j2len = new Map();
    for (let i = alo; i < ahi; i += 1) {
      const newj2len = new Map();
      for (const j of b2j.get(a[i]) || []) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) || 0) + 1;
        newj2len.set(j, k);
        if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
      }
      j2len = newj2len;
    }
    return [besti, bestj, bestsize];
  };
  const queue = [[0, a.length, 0, b.length]];
  const blocks = [];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = longest(alo, ahi, blo, bhi);
    if (k) {
      blocks.push(k);
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return blocks.reduce((x, y) => x + y, 0);
}
const ratio = (a, b) => (a.length + b.length === 0 ? 1 : (2 * matchingBlocks(a, b)) / (a.length + b.length));

function stripLegal(name) {
  let text = stripEmoji(name).trim().toLowerCase();
  const suffixes = [...LEGAL_SUFFIXES].sort((x, y) => y.length - x.length);
  for (let pass = 0; pass < 2; pass += 1) {
    for (const suffix of suffixes) {
      if (text.endsWith(` ${suffix}`)) text = text.slice(0, -suffix.length).replace(/^[ ,.]+|[ ,.]+$/g, '');
    }
  }
  return text.replace(/\s+/g, ' ');
}
function matchCompany(raw, canonical) {
  if (isBlank(raw)) return '';
  const cleaned = stripLegal(String(raw));
  const byNorm = new Map(canonical.map((c) => [stripLegal(c), c]));
  if (byNorm.has(cleaned)) return byNorm.get(cleaned);
  const prefixed = [...byNorm].filter(([n]) => n.startsWith(`${cleaned} `)).map(([, c]) => c);
  if (prefixed.length === 1) return prefixed[0];
  const squashed = cleaned.replace(/ /g, '');
  let best = ''; let score = 0;
  for (const [norm, canon] of byNorm) {
    const r = ratio(squashed, norm.replace(/ /g, ''));
    if (r > score) { best = canon; score = r; }
  }
  return score >= 0.86 ? best : '';
}
function rootDomain(raw) {
  if (isBlank(raw)) return '';
  const text = String(raw).trim().toLowerCase().replace(/^[a-z]+:\/\//, '');
  return text.split(/[/?#]/)[0].replace(/^www\./, '');
}
function sizeBucket(value) {
  if (isBlank(value)) return '';
  const nums = (String(value).match(/\d[\d,]*/g) || []).map((n) => parseInt(n.replace(/,/g, ''), 10));
  if (!nums.length) return '';
  const count = nums.length === 1 ? nums[0] : Math.floor((nums[0] + nums[1]) / 2);
  for (const [upper, label] of SIZE_BUCKETS) if (count <= upper) return label;
  return SIZE_TOP;
}
function cityCountry(raw) {
  if (isBlank(raw)) return ['', ''];
  const low = stripEmoji(String(raw)).toLowerCase();
  const first = low.split(',')[0].trim();
  if (CITY_INFO[first]) return CITY_INFO[first];
  for (const key of CITY_KEYWORDS) if (low.includes(key)) return CITY_INFO[key];
  return ['', ''];
}
const countryName = (raw) => COUNTRY_ALIASES[String(raw || '').trim().toLowerCase()] || '';
