// ---- enrichment + merge into one row per person (port of pipeline/build.py) ----
const COLUMNS = ['Company Name', 'Website', 'HQ Location', 'Company Size', 'Contact Person Name', 'First Name',
  'Last Name', 'Designation/Job Title', 'LinkedIn URL', 'Mobile No.', 'Email ID'];
const STRUCTURED = { 'LinkedIn Lead Gen Form': 0, ZoomInfo: 1, Apollo: 2, 'LinkedIn Scraped': 3,
  'Event Delegate': 4, 'Event Booth Scan': 5, 'Google Ads': 6 };
const when = (p) => (p.date === null || p.date === undefined ? -Infinity : p.date);

function mostCommon(values) {
  const counts = new Map();
  values.forEach((v) => counts.set(v, (counts.get(v) || 0) + 1));
  let best = ''; let top = 0;
  for (const [v, c] of counts) if (c > top) { best = v; top = c; }
  return best;
}
function cmp(a, b) {
  if (Array.isArray(a)) {
    for (let i = 0; i < a.length; i += 1) { const c = cmp(a[i], b[i]); if (c) return c; }
    return 0;
  }
  const x = typeof a === 'boolean' ? Number(a) : a; const y = typeof b === 'boolean' ? Number(b) : b;
  return x === y ? 0 : (x > y ? 1 : -1);
}
function argmax(keys, keyFn) {
  let best; let bestKey;
  for (const k of keys) {
    const kk = keyFn(k);
    if (best === undefined || cmp(kk, bestKey) > 0) { best = k; bestKey = kk; }
  }
  return best;
}
function hqOf(city, country) {
  const [canonCity, canonCountry] = cityCountry(city);
  const c = canonCity || city; const k = country || canonCountry;
  return c && k ? `${c}, ${k}` : '';
}

// Rule 4: ZoomInfo first, then Apollo, then everything else.
function companyFacts(company, allPreps) {
  const at = allPreps.filter((p) => p.company_c === company);
  const facts = { 'Company Name': company, Website: '', 'HQ Location': '', 'Company Size': '' };
  for (const source of ['ZoomInfo', 'Apollo']) {
    const rows = at.filter((p) => p.source === source);
    if (!facts.Website) facts.Website = mostCommon(rows.filter((r) => r.co_website).map((r) => rootDomain(r.co_website)));
    if (!facts['HQ Location']) {
      facts['HQ Location'] = hqOf(mostCommon(rows.filter((r) => r.co_city).map((r) => r.co_city)),
        mostCommon(rows.filter((r) => r.co_country).map((r) => r.co_country)));
    }
    if (!facts['Company Size']) facts['Company Size'] = mostCommon(rows.map((r) => sizeBucket(r.co_size_raw)).filter(Boolean));
  }
  if (!facts['Company Size']) facts['Company Size'] = mostCommon(at.map((p) => sizeBucket(p.co_size_raw)).filter(Boolean));
  if (!facts['HQ Location']) {
    facts['HQ Location'] = mostCommon(at.filter((p) => cityCountry(p.co_loc_raw)[0]).map((p) => hqOf(...cityCountry(p.co_loc_raw))));
  }
  return facts;
}

// Rule 3: most recent dated source wins for employer, then title at that employer.
function currentJob(cluster) {
  const dated = cluster.filter((p) => p.company_c).sort((a, b) => when(b) - when(a) || 0);
  const company = dated[0].company_c;
  const titled = dated.filter((p) => p.company_c === company && p.title_c);
  return [company, titled.length ? titled[0].title_c : ''];
}
function pickName(cluster) {
  const slugs = [...new Set(cluster.map((p) => p.slug).filter(Boolean))];
  let cands = cluster.filter((p) => p.full).map((p) => [p.full, STRUCTURED[p.source]]);
  if (slugs.length) {
    const target = letters(slugToName(slugs[0]));
    const matched = cands.filter((c) => letters(c[0]) === target);
    if (matched.length) cands = matched;
  }
  const counts = new Map();
  cands.forEach(([n]) => counts.set(n, (counts.get(n) || 0) + 1));
  const best = argmax([...counts.keys()], (n) => [counts.get(n), -Math.min(...cands.filter((c) => c[0] === n).map((c) => c[1]))]);
  for (const p of cluster) {
    if (p.first && p.last && letters(p.first + p.last) === letters(best)) return [best, p.first, p.last];
  }
  const idx = best.indexOf(' ');
  return idx < 0 ? [best, best, ''] : [best, best.slice(0, idx), best.slice(idx + 1)];
}
function pickEmail(cluster, domain) {
  const flags = []; const score = new Map();
  for (const p of cluster) {
    for (const [email, status] of p.emails_v) {
      const rank = [email.split('@')[1] === domain, !isPersonalDomain(email)];
      const old = score.get(email) || [rank, 0, -Infinity, status];
      const merged = old[3] === 'ok' || status === 'ok' ? 'ok' : 'repaired';
      score.set(email, [rank, old[1] + 1, Math.max(old[2], when(p)), merged]);
    }
  }
  if (!score.size) return ['', ['no valid email in any source']];
  const best = argmax([...score.keys()], (e) => score.get(e).slice(0, 3));
  const [rank, , , status] = score.get(best);
  if (status === 'repaired') flags.push(`email typo repaired to ${best} (domain confirmed from ZoomInfo/Apollo)`);
  if (!rank[1]) flags.push('personal email used: no work email in any source');
  else if (!rank[0]) flags.push("work email is on a previous employer's domain: no current-employer email found");
  return [best, flags];
}
function pickMobile(cluster) {
  const seen = new Map(); const flags = []; const usable = new Map();
  for (const p of cluster) {
    for (const [number, kind] of p.phones_v) {
      if (!seen.has(number)) seen.set(number, []);
      seen.get(number).push(kind);
    }
  }
  for (const [number, kinds] of seen) {
    if (kinds.every((k) => k === 'apollo_direct')) {
      flags.push(`${number} only in Apollo 'Work Direct Phone' (uncorroborated): excluded as a direct line`);
      continue;
    }
    usable.set(number, [kinds.includes('mobile'), kinds.length]);
  }
  if (!usable.size) return ['', flags.length ? flags : ['no mobile number in any source']];
  return [argmax([...usable.keys()], (n) => usable.get(n)), flags];
}
function buildPerson(cluster, allPreps) {
  const [company, title] = currentJob(cluster);
  const facts = companyFacts(company, allPreps);
  const [name, first, last] = pickName(cluster);
  const slugs = [...new Set(cluster.map((p) => p.slug).filter(Boolean))].sort();
  const [email, flags] = pickEmail(cluster, facts.Website);
  const [mobile, mflags] = pickMobile(cluster);
  const companies = [...new Set(cluster.map((p) => p.company_c).filter(Boolean))].sort();
  if (companies.length > 1) flags.push(`employer changed across sources: latest dated source used (${companies.join(' / ')})`);
  if (!slugs.length) flags.push('no public LinkedIn slug in any source (Sales Navigator / ACwAA ids only)');
  const row = { ...facts, 'Contact Person Name': name, 'First Name': first, 'Last Name': last,
    'Designation/Job Title': title, 'LinkedIn URL': slugs.length ? linkedinUrl(slugs[0]) : '',
    'Mobile No.': mobile, 'Email ID': email };
  return { row, flags: [...flags, ...mflags], refs: cluster.map((p) => `${p.source}: ${p.ref}`) };
}
