// STEP 3 - Standardize to the Rules tab: company name, job title, email, E.164 mobile, city/country.
const recs = $input.all().map((it) => it.json);

// Company universe: ZoomInfo names first, then Apollo (rule 4). Used to fix typos / suffixes / short names.
const hqCountry = new Map();
const domains = new Set();
for (const source of ['ZoomInfo', 'Apollo']) {
  for (const r of recs.filter((x) => x.source === source)) {
    if (!hqCountry.has(r.company.trim())) hqCountry.set(r.company.trim(), countryName(r.co_country));
    domains.add(rootDomain(r.co_website));
  }
}
domains.delete('');
const canonical = [...hqCountry.keys()];

return recs.map((r) => {
  const company_c = matchCompany(r.company, canonical);
  const [p_city, locCountry] = cityCountry(r.person_loc);
  const p_country = countryName(r.country) || locCountry || hqCountry.get(company_c) || '';
  const emails_v = [];
  for (const raw of r.emails) {
    for (const cand of splitEmails(raw)) {
      const [status, fixed] = classifyEmail(cand, domains);
      if (status === 'ok' || status === 'repaired') emails_v.push([fixed, status]);
    }
  }
  const phones_v = [];
  for (const [raw, kind] of r.phones) {
    const [e164] = parseMobile(raw, p_country);
    if (e164) phones_v.push([e164, kind]);
  }
  return { json: { ...r, company_c, title_c: canonicalTitle(r.title), emails_v, phones_v, p_city, p_country,
    co_country: countryName(r.co_country) } };
});
