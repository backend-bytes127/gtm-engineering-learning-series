// STEP 2 - Clean fields and REMOVE invalid records (test, spam, job seekers, hidden members, no company).
function invalidReason(r, full) {
  if (r.is_test) return 'test/spam lead';
  const text = `${full} ${r.company} ${r.title} ${r.emails.join(' ')}`.toLowerCase();
  if (/\b(test|asdf|qa)\b|\.invalid/.test(text)) return 'test/spam lead';
  if (/looking for job|job seek|\bstudent\b|\bfreelanc/.test(text)) return 'job seeker / freelancer';
  if (full.trim().toLowerCase() === 'linkedin member') return 'hidden LinkedIn Member';
  // A blank company is NOT rejected here: it may be enriched from another source in step 5.
  if (['self', 'none', 'n/a', '-'].includes(r.company.trim().toLowerCase())) return 'no company';
  return '';
}
function resolveNames(r) {
  const first = cleanName(r.first_raw);
  const last = cleanName(r.last_raw);
  if (r.name_mode === 'pair') return { first, last, full: `${first} ${last}`.trim() };
  if (r.name_mode === 'pair+full') return { first, last, full: cleanName(r.full_raw) };
  return { first: '', last: '', full: cleanName(r.full_raw) };
}
return $input.all().map(({ json: r }) => {
  const { first, last, full } = resolveNames(r);
  const slug = r.li_urls.map(linkedinSlug).find(Boolean) || '';
  const acwaa = linkedinAcwaa(r.li_urls.map((u) => s(u)).join(' '));
  const reason = invalidReason(r, full);
  return { json: { ...r, first, last, full, slug, acwaa, status: reason ? 'removed' : 'kept', reason } };
});
