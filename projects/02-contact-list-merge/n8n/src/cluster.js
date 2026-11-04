// ---- same-person grouping (port of pipeline/cluster.py) ----
class Groups {
  constructor(preps) {
    this.parent = preps.map((_, i) => i);
    this.slugs = preps.map((p) => new Set(p.slug ? [p.slug] : []));
    this.acwaa = preps.map((p) => new Set(p.acwaa ? [p.acwaa] : []));
    this.refused = [];
  }

  find(i) {
    let x = i;
    while (this.parent[x] !== x) { this.parent[x] = this.parent[this.parent[x]]; x = this.parent[x]; }
    return x;
  }

  disjoint(a, b) {
    return a.size > 0 && b.size > 0 && ![...a].some((v) => b.has(v));
  }

  union(i, j, why) {
    const ri = this.find(i); const rj = this.find(j);
    if (ri === rj) return true;
    if (this.disjoint(this.slugs[ri], this.slugs[rj]) || this.disjoint(this.acwaa[ri], this.acwaa[rj])) {
      this.refused.push([i, j, why]);
      return false;
    }
    this.parent[rj] = ri;
    this.slugs[rj].forEach((v) => this.slugs[ri].add(v));
    this.acwaa[rj].forEach((v) => this.acwaa[ri].add(v));
    return true;
  }
}

function strongKeys(p) {
  return [
    ...p.emails_v.map(([e]) => `email:${e}`),
    ...p.phones_v.map(([ph]) => `phone:${ph}`),
    ...(p.slug ? [`slug:${p.slug}`] : []),
    ...(p.acwaa ? [`acwaa:${p.acwaa}`] : []),
  ];
}
function lastOf(p) {
  if (p.last && p.first) return p.full.startsWith(p.first) ? p.full.slice(p.first.length).trim() : p.last;
  const idx = p.full.indexOf(' ');
  return idx >= 0 ? p.full.slice(idx + 1) : '';
}
const keyOf = (p) => nameKey(p.first || p.full.split(' ')[0], lastOf(p));
const sameName = (a, b) => keyOf(a) === keyOf(b);

function buildClusters(preps) {
  const groups = new Groups(preps);
  const links = [];
  const seen = new Map();
  preps.forEach((p, i) => {
    for (const key of strongKeys(p)) {
      if (seen.has(key)) groups.union(seen.get(key), i, key); else seen.set(key, i);
    }
  });
  for (let i = 0; i < preps.length; i += 1) {
    for (let j = i + 1; j < preps.length; j += 1) {
      const a = preps[i]; const b = preps[j];
      if (groups.find(i) === groups.find(j) || !a.company_c || a.company_c !== b.company_c) continue;
      if (sameName(a, b) && (!a.title_c || !b.title_c || a.title_c === b.title_c) && groups.union(i, j, 'name+company+title')) {
        links.push({ kind: 'name+company+title', a: a.ref, b: b.ref, note: `${a.full} @ ${a.company_c} (${a.title_c || b.title_c})` });
      }
    }
  }
  for (let i = 0; i < preps.length; i += 1) {
    for (let j = i + 1; j < preps.length; j += 1) {
      const a = preps[i]; const b = preps[j];
      if (groups.find(i) === groups.find(j) || !a.company_c || !b.company_c) continue;
      if (a.company_c !== b.company_c && a.p_city && a.p_city === b.p_city && sameName(a, b) && groups.union(i, j, 'job-change')) {
        links.push({ kind: 'job-change (verify)', a: a.ref, b: b.ref, note: `${a.full}: ${a.company_c} / ${b.company_c}, both in ${a.p_city}` });
      }
    }
  }
  const buckets = new Map();
  preps.forEach((p, i) => {
    const root = groups.find(i);
    if (!buckets.has(root)) buckets.set(root, []);
    buckets.get(root).push(p);
  });
  for (const [i, j, why] of groups.refused) {
    links.push({ kind: 'REFUSED merge', a: preps[i].ref, b: preps[j].ref, note: `${why}: different LinkedIn identities` });
  }
  return { clusters: [...buckets.values()], links };
}
