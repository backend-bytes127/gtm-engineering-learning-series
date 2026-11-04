# Rules traceability matrix

Every line of the specification (the template's **Rules** tab) mapped to the code that implements it and the tests that guard it. If a rule changes, this table shows what to touch.

Locations: Python in `pipeline/`, JavaScript in `n8n/src/`. Tests are in `pipeline/tests/`.

## Field rules

| Field | Rule (summary) | Implementation | Tests |
|---|---|---|---|
| Company Name | One name per company; drop legal suffixes; fix casing and typos; current name | `normalize.match_company`, `_strip_legal`; name chosen from ZoomInfo then Apollo in `build.company_facts` / `company.js` | `test_match_company`, `test_company_facts_prefer_zoominfo_then_apollo_then_rest`, `test_formats` |
| Website | Root domain, lowercase, no scheme/www/path/params; LinkedIn company pages are not websites | `normalize.root_domain`; only ZoomInfo/Apollo `Website` is read, scraped company URLs are ignored | `test_domain_size_location`, `test_formats` (regex) |
| HQ Location | `City, Country`, official current city name, **company** HQ not contact's | `constants.CITY_INFO`, `normalize.city_country`, `build._hq` | `test_domain_size_location` (Madras to Chennai), `test_company_facts_*`, `test_formats` |
| Company Size | One of eight buckets | `normalize.size_bucket` | `test_domain_size_location` (boundaries, `SMB` ignored), `test_size_falls_back_to_form_ranges_but_ignores_smb_labels`, `test_formats` |
| Contact Person Name | Formal first + last, proper case, as on the LinkedIn slug; no salutations, credentials, pronouns, emoji | `normalize.clean_name`, `slug_to_name`, `build._name` | `test_clean_name`, `test_name_follows_linkedin_slug_spelling_and_keeps_two_word_names`, `test_formats` (no leaked noise) |
| First Name / Last Name | Two-word given and family names; single initial allowed | structured first/last pair preferred in `build._name` | same as above; golden file |
| Designation/Job Title | Full spelled-out title; headline removed; abbreviations expanded | `normalize.canonical_title`, `constants.TOKEN_EXPANSIONS` | `test_canonical_title` (18 cases), `test_formats` (no abbreviations) |
| LinkedIn URL | `https://www.linkedin.com/in/<slug>`, no trailing slash/params/country subdomain; Sales Nav and `ACwAA` ids do not count | `normalize.linkedin_slug`, `linkedin_url` | `test_linkedin`, `test_formats` (`acwa` never appears) |
| Mobile No. | E.164, mobile only; no board or direct lines | `normalize.parse_mobile`; column trust in [ADR-0004](../../../docs/adr/0004-mobile-only-phone-policy-with-corroboration.md); `build._mobile` | `test_parse_mobile_valid`, `test_parse_mobile_rejected`, `test_mobile_prefers_mobile_columns_and_excludes_uncorroborated_direct_dial`, `test_apollo_direct_accepted_when_another_source_has_the_same_number`, `test_formats` |
| Email ID | Lowercase, one address; valid work e-mail first, personal only if no work e-mail; blank if none valid | `normalize.split_emails`, `classify_email`; `build._email` | `test_emails`, `test_email_prefers_current_domain_work_over_personal_and_old_employer`, `test_email_personal_used_only_when_no_work_email_and_is_flagged`, `test_repaired_email_is_flagged_but_clean_duplicate_cancels_the_flag` |

## Merge rules

| # | Rule | Implementation | Tests |
|---|---|---|---|
| 1 | One row per real person, duplicates merged across all files and tabs | `cluster.build_clusters`; `build.build_all` | `test_no_duplicate_people` (no repeated e-mail, LinkedIn URL or mobile), golden file (12 people) |
| 2 | Same person when e-mail or LinkedIn slug matches; name + company alone needs a second check | strong keys, pass 2 (compatible title) and the slug **guard** in `cluster._Groups.union` | `test_shared_email_merges`, `test_shared_slug_merges_across_name_spellings`, `test_shared_mobile_links_personal_and_work_email_records`, `test_merge_refused_when_linkedin_slugs_differ_even_if_email_shared`, `test_same_name_same_company_different_titles_stay_separate`, `test_same_name_same_company_compatible_title_merges`, `test_name_twins_stay_separate` |
| 3 | When sources disagree on employer or title, the most recent dated source wins; date formats differ per file | per-source date parsers in `loaders.py` / `n1_map.js`; `build._current` | `test_latest_dated_source_wins_for_employer_and_title`, `test_undated_source_ranks_below_any_dated_source`, `test_title_comes_from_the_current_employer_not_an_older_one`, `test_latest_employer_wins_for_a_job_changer`, `test_job_change_*` |
| 4 | Company facts: ZoomInfo first, then Apollo, then everything else | `build.company_facts` | `test_company_facts_prefer_zoominfo_then_apollo_then_rest`, `test_company_facts_fall_back_to_apollo_when_zoominfo_absent` |
| 5 | Enrich by filling gaps from other sources; blank when no source has it; never guess | `build._name/_email/_mobile` pick from other records' values; [ADR-0007](../../../docs/adr/0007-blank-over-guess-and-review-flags.md) | golden file; the three flag tests above |
| 6 | Remove test leads, spam, job seekers, individuals with no company, hidden LinkedIn Member rows | `loaders.invalid_reason`; post-merge company check in `build.build_all` | `test_invalid_reasons` (7 cases), `test_blank_company_is_not_rejected_up_front`, `test_load_all_counts_on_sample_data` (37 rows, 5 removed, 2 hidden members) |

## Cross-implementation guarantee

Every row above is implemented twice (Python and JavaScript). `make parity` runs the generated n8n Code nodes on the sample data and requires the result to equal `expected-output/Final_Contact_List.xlsx` cell for cell; `make e2e` repeats that inside a real n8n container.
