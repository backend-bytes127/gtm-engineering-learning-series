// STEP 4 - Remove duplicates: group every record that describes the same real person.
// Same person = same email, LinkedIn slug, Sales-Nav id or mobile. Name+company needs a compatible title.
// A merge is REFUSED if it would join two different LinkedIn identities (name twins stay separate).
const preps = $input.all().map((it) => it.json);
const { clusters, links } = buildClusters(preps);
return [
  ...clusters.map((members) => ({ json: { type: 'person', members } })),
  ...links.map((l) => ({ json: { type: 'link-decision', ...l } })),
];
