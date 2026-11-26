# Holdout test design: does this channel cause conversions?

Attribution says who touched the buyer. Only a randomised holdout says what would have happened without the channel.

## Plan to write down before launch

| Item | Rule |
|---|---|
| Question | "How many extra conversions per eligible unit does channel X cause, against not running it?" One channel per test |
| Unit | The smallest unit you can really switch off: user or account for e-mail and audience ads; region for search, TV or broad social. In B2B, randomise accounts, not people, so colleagues do not cross arms |
| Eligibility | Fixed **before** exposure, from data both arms have. Never "people who saw the ad" |
| Assignment | `attribution.holdout.assign(unit_id, salt, fraction)`: a salted hash, stable across runs; a new salt for every test |
| Holdout size | 10% to 50%. A larger holdout needs fewer units in total but gives up more of the channel while the test runs |
| Primary metric | One conversion, one source of record (for example CRM opportunities created), counted for every assigned unit |
| Estimate | Intention-to-treat: rate in treatment minus rate in holdout, with a 95% interval (`analyse`) |
| Duration | Exposure period plus the conversion lag (or sales cycle). Do not stop early because the interval looks good |
| Sample size | `required_total(rate_with, rate_without, fraction)` using the smallest lift that would change the budget, not the lift you hope for |
| Decision rule | Written in advance. Example: keep if the lower end of cost per incremental conversion is below the target; cut if even the upper end of the effect is too small to pay back; otherwise inconclusive, and say so |

## Checks

1. **A/A first.** Assign arms, change nothing, and confirm the difference is near zero.
2. **Sample-ratio mismatch.** Run `sample_ratio_p`; stop and fix assignment if p < 0.001.
3. **Delivery.** Confirm from platform logs that the holdout got no ads or e-mail from this channel.
4. **Contamination.** List how the holdout could still be reached (second device, shared inbox, a colleague, overlap between campaigns). It usually pulls the estimate towards zero.
5. **Balance.** Compare pre-period conversion and account size across arms.
6. **One test at a time per unit,** or randomise the tests independently and say so.

## By channel

| Channel | Design | Main trap |
|---|---|---|
| E-mail, lifecycle | User or account holdout | Transactional mail must still go to both arms |
| Retargeting | Split the eligible audience before bidding; ghost ads or public-service ads if the platform offers them | Comparing reached with unreached people |
| Paid social, display | Platform lift study, or regions | Platform-reported "lift" with an undisclosed method |
| Brand search | Region holdout: pause in some matched regions | Organic and direct picking up the clicks, which is the point of measuring total conversions |
| Non-brand search | Region holdout | Spillover between regions |
| Webinar | Randomise the **invitation**; the effect of attending needs an extra assumption (instrumental variable) | Comparing attendees with non-attendees |

This repository implements only the user-level design. **Region (geo) tests need their own analysis** (few units, matched markets or synthetic control, randomisation inference) and the formulas here do not apply to them.

## What the planted world shows about cost

Synthetic: about 4.1% of users convert with everything on; 20% holdout; two-sided 5% test; 80% power. The full table is section 5 of `reports/report.md`. Small effects need very large samples: about 188,000 users in total for paid social, 475,000 for retargeting and 2.8 million for display. If a real programme cannot reach the sample size, the honest answer is "we cannot measure this", not a smaller test read optimistically.

## Not valid

- Pausing a channel and comparing with last month (season, pipeline mix and other launches move too).
- Exposed against unexposed users. In the planted world this shows a 6.7 point gap for brand search, whose true effect is zero.
- Reading many segments until one is significant.
