// STEP 6 - Final Output: exactly the 11 template columns, in template order (audit fields stay on the previous node).
return $input.all().map(({ json }) => ({ json: Object.fromEntries(COLUMNS.map((c) => [c, json[c] ?? ''])) }));
