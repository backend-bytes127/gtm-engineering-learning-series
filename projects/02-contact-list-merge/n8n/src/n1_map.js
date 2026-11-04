// STEP 1 - Map each source's columns onto ONE common record shape. Raw values only; no cleaning yet.
const IST_MS = 330 * 60000;
const EVENT_END = Date.UTC(2026, 8, 19); // delegate list has no per-row date; summit ran 18-19 Sep 2026
const rowsOf = (node) => $(node).all().map((it) => it.json);
const utc = (y, mo, d, h = 0, mi = 0, sec = 0) => Date.UTC(+y, +mo - 1, +d, +h, +mi, +sec);

const dateGoogleAds = (t) => { // '2026-10-12 13:09:15 IST'
  const m = s(t).replace(' IST', '').match(/(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)/);
  return m ? utc(...m.slice(1)) - IST_MS : null;
};
const dateScan = (t) => { // '18/09/2026 13:25' (dd/mm/yyyy)
  const m = s(t).match(/(\d\d)\/(\d\d)\/(\d{4}) (\d\d):(\d\d)/);
  return m ? utc(m[3], m[2], m[1], m[4], m[5]) - IST_MS : null;
};
const dateLinkedInForm = (t) => { // '10/04/2026, 01:48 AM' (mm/dd/yyyy)
  const m = s(t).match(/(\d\d)\/(\d\d)\/(\d{4}), (\d\d):(\d\d) (AM|PM)/);
  if (!m) return null;
  const hour = (+m[4] % 12) + (m[6] === 'PM' ? 12 : 0);
  return utc(m[3], m[1], m[2], hour, m[5]);
};
const dateIso = (t) => (s(t) ? Date.parse(`${s(t).slice(0, 19)}Z`) : null);

const base = (o) => ({ name_mode: 'full', first_raw: '', last_raw: '', full_raw: '', emails: [], phones: [],
  company: '', title: '', li_urls: [], person_loc: '', country: '', co_size_raw: '', co_website: '',
  co_city: '', co_country: '', co_loc_raw: '', is_test: false, date: null, ...o });
const out = [];
const add = (source, n, o) => out.push({ json: base({ source, ref: `${source} row ${n}`, ...o }) });

rowsOf('Extract Google Ads').forEach((r, i) => add('Google Ads', i + 1, {
  date: dateGoogleAds(r['Time submitted']), full_raw: r['Full name'], emails: [s(r['Work email'])],
  phones: [[s(r['Phone number']), 'self']], company: s(r['Company name']), title: s(r['Job title']),
  person_loc: s(r.City), co_size_raw: s(r['How many employees does your company have?']),
  is_test: String(r['Is test']).toUpperCase() === 'TRUE',
}));
rowsOf('Extract Event Delegates').filter((r) => /^\d+$/.test(s(r['S.No']))).forEach((r, i) => add('Event Delegate', i + 1, {
  date: EVENT_END, full_raw: r['Name of Delegate'], emails: [s(r['Email ID'])], phones: [[s(r['Contact No']), 'self']],
  company: s(r.Organisation), title: s(r.Designation), person_loc: s(r.City), co_size_raw: s(r['Emp Strength']),
}));
rowsOf('Extract Event Scans').forEach((r, i) => {
  const phones = [[s(r.Phone), 'self']];
  const noted = phoneFromNotes(r.Notes); // phone typed into the Notes column
  if (noted) phones.push([noted, 'self']);
  add('Event Booth Scan', i + 1, { date: dateScan(r['Scan Time']), full_raw: r['Full Name'], emails: [s(r.Email)],
    phones, company: s(r.Company), title: s(r['Job Title']) });
});
rowsOf('Extract LinkedIn Form').forEach((r, i) => add('LinkedIn Lead Gen Form', i + 1, {
  date: dateLinkedInForm(r['Submitted At']), name_mode: 'pair', first_raw: r['First Name'], last_raw: r['Last Name'],
  emails: [s(r['Email Address'])], phones: [[s(r['Phone Number']), 'self']], company: s(r['Company Name']),
  title: s(r['Job Title']), li_urls: [r['LinkedIn Profile']], person_loc: s(r.City), country: s(r.Country),
  co_size_raw: s(r['Company Size']),
}));
rowsOf('Extract Scraped LinkedIn').forEach((r, i) => add('LinkedIn Scraped', i + 1, {
  date: dateIso(r.timestamp), name_mode: 'pair+full', first_raw: r.firstName, last_raw: r.lastName, full_raw: r.fullName,
  company: s(r.companyName), title: s(r.title), li_urls: [r.defaultProfileUrl, r.linkedInProfileUrl, r.profileUrl],
  person_loc: s(r.location), co_loc_raw: s(r.companyLocation),
}));
rowsOf('Extract Apollo').forEach((r, i) => add('Apollo', i + 1, {
  date: dateIso(r['Primary Email Last Verified At']), name_mode: 'pair', first_raw: r['First Name'], last_raw: r['Last Name'],
  emails: [s(r.Email)], phones: [[s(r['Mobile Phone']), 'mobile'], [s(r['Work Direct Phone']), 'apollo_direct']],
  company: s(r.Company), title: s(r.Title), li_urls: [r['Person Linkedin Url']], person_loc: s(r.City), country: s(r.Country),
  co_size_raw: s(r['# Employees']), co_website: s(r.Website), co_city: s(r['Company City']), co_country: s(r['Company Country']),
}));
rowsOf('Extract ZoomInfo').forEach((r, i) => add('ZoomInfo', i + 1, { // ZoomInfo has no populated date -> null
  name_mode: 'pair', first_raw: r['First Name'], last_raw: r['Last Name'], emails: [s(r['Email Address'])],
  phones: [[s(r['Mobile phone']), 'mobile']], // 'Direct Phone Number' deliberately NOT read (direct line)
  company: s(r['Company Name']), title: s(r['Job Title']), li_urls: [r['LinkedIn Contact Profile URL']],
  person_loc: s(r['Person City']), country: s(r.Country), co_size_raw: s(r.Employees), co_website: s(r.Website),
  co_city: s(r['Company City']), co_country: s(r['Company Country']),
}));
return out;
