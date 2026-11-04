// STEP 5 - Enrich gaps from other sources and merge each group into ONE row.
// Employer/title: latest dated source. Company facts: ZoomInfo > Apollo > rest. Email: current-domain work email first.
// Mobile only (no board/direct lines). Anything no source has stays blank.
const groups = $input.all().map((it) => it.json).filter((j) => j.type === 'person').map((j) => j.members);
const allPreps = groups.flat();
const people = groups
  .filter((g) => g.some((p) => p.company_c)) // a person with no company in ANY source is dropped
  .map((g) => buildPerson(g, allPreps))
  .sort((a, b) => cmp([a.row['Company Name'], a.row['Last Name'], a.row['First Name']],
    [b.row['Company Name'], b.row['Last Name'], b.row['First Name']]));
return people.map((p) => ({ json: { ...p.row, _flags: p.flags, _merged_from: p.refs } }));
