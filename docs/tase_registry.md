# NEWS / Rosario — שכבת הגנה TASE: מניות לפסילה, אג״ח להתראה

**Status (2026-11-23): MERGED IN PUBLIC NEWS; PRIVATE ROSARIO BOARD HOOKS NOT CONNECTED.** The read-only GitHub smoke and independent 17-company live acceptance tests have both passed using the new credential; PR #1 was merged to NEWS main and no official licensed snapshot has been committed. The committed JSON intentionally contains **zero companies**, with run_status=failed. The real-data smoke test has successfully built the registry, but the snapshot intentionally stays **temporary inside GitHub Actions**. The committed placeholder is not a working production exclusion list. An approved private distribution/storage mechanism must be chosen before Rosario agents can consume it.

## What the module does

One public data file: **data/latest/tase_registered_securities.json** (root metadata plus rows). Each row has the Hebrew/English company names, corporate ID (ח.פ.), issuer ID, company-wide type (מניה / אג"ח / שניהם), security type, security number, security name, ISIN, observation date, update date and official TASE links. The file root includes last_updated, source_as_of, row_count, run_status (success/failed), last_attempt_at, last_error and coverage diagnostics.

| Lookup outcome | Required downstream action |
| --- | --- |
| **Confirmed publicly traded shares** (exact matching corporate ID, no conflicting name) | **Reject / remove from lead lists**, with TASE evidence and audit note. A company with both shares and bonds is rejected due to shares. |
| **Confirmed corporate bonds only** (exact matching corporate ID, no conflicting name) | **Keep company**; mark as `bond_warning` and `scoring_signal="strong_negative"`. Existing lead scoring controls the numerical penalty; this safety layer MUST NOT invent or overwrite a numeric score. |
| **Name-only match, mismatched ID/name, ambiguous issuer** | Manual confirmation; no automatic rejection and no confirmed bond-scoring penalty. |
| **Not found** | Continue existing checks. No inference that company is private or has never issued corporate bonds. |
| **Registry missing/stale/error** | Manual review / unavailable alert; never automatic rejection; preserve original lead. |

Name-only lookup accepts the official short company name **or** the full registered Hebrew/English `companyFullName`, normalizing punctuation and Hebrew בע"מ/בעמ. It returns the observed `type` but **always** sets `requires_review=true` and `auto_disqualify=false`. In case the same input name resolves to multiple issuers, `type="לא חד-משמעי"` and no collective share/bond status is inferred. Fuzzy/substring names are not claimed exact.

**Verified 2026-11-23 classification fix:** Use the TASE official four-digit `securityFullTypeCode` as primary truth (01xx stocks except 0113 fund; 03xx convertible bonds; 05xx corporate bonds except 0504 tracking certificate, 0506 deposit certificate, 0508 commercial paper and 0512 debt participation). The earlier text-only classifier missed stock code **0104** (Leumi), and could label tracking certificates/ETFs as shares or bonds. The corrected live run identifies Leumi, Hapoalim and Mizrahi-Tefahot as `שניהם`, while Electricity Corporation and Mizrahi-Tefahot Issuances are `אג"ח` in observed TASE records.

**Name-only acceptance (latest run 45153674425):** 20/20 real company-name queries matched expected corporate IDs and returned stock/bond type, including shortened and full registered company names; 25/25 deterministic unit tests passed; 3 known banks had both share and bond records. `RNEWS_TASE_2026` is the sole workflow secret used.

Only an unambiguous exact 9-digit corporate-ID match **to equity securities** can authorize auto-disqualification. Exact matching corporate bonds without equity produce an alert only. Exact normalized names can return matches but require review. Similar/fuzzy names never auto-disqualify. If the input company name conflicts with a matching ID, review is required.

## Official sources and crucial limitation

Automated source is TASE **Data Hub / DataWise Securities - Basic**, strictly these GET routes:

- https://datawise.tase.co.il/v1/basic-securities/companies-list
- https://datawise.tase.co.il/v1/basic-securities/securities-types
- https://datawise.tase.co.il/v1/basic-securities/trade-securities-list/{year}/{month}/{day}

Developer portal: https://datahubapi.tase.co.il

Official site references:
- https://market.tase.co.il/he/market_data/tase-companies/public
- https://market.tase.co.il/he/market_data/securities/info/all?cl1=0&dType=1

**Verified coverage gap (Nov 23 live run):** the official company list contains **693** issuers, while **661** issuers had at least one securely classified observed share/bond; **32** official-list issuers therefore lack a positive share/bond classification in this snapshot. There are additionally **42 unlinked security observations**. These require further investigation and must not be treated as private companies or no-bond evidence.

**Important for the business use case:** “already issued a bond” is a historical question. The date-based trade list confirms only observed recently traded bonds; it CANNOT rule out historical debt issuance, matured/retired bonds, suspended or illiquid series. Never claim that a company has never issued bonds. The date-based trade list is a union of recently *traded* securities, not a complete list of all *registered* securities. It can establish reliable issuer-linked **positives** but does not prove a company has no bonds/shares, particularly suspended or illiquid securities. Do not upgrade the coverage to exhaustive without verifying a full official active-listing export or endpoint. No fake source results are created.

Official Data Hub access may require an application, subscription/approval and adherence to use/redistribution terms. No bot protection bypass, browser automation or alternative unlicensed source is attempted. Any 401/403/429 stops immediately.

## Installation and weekly operation

1. Register legally for the official TASE Data Hub **Securities - Basic** API product.
2. Save the actual key as a GitHub Actions repository secret named **RNEWS_TASE_2026**. The workflow maps this secret to the Python process environment variable `TASE_API_KEY`. Do not commit it to the public NEWS repository.
3. Once merged, run the **TASE official exclusion registry** GitHub workflow manually. Its normal schedule is Friday 08:17 UTC (10:17 Israel winter / 11:17 Israel summer), before the Saturday leads cycle. **This job validates a temporary snapshot only; it neither commits raw TASE data nor uploads it as a public artifact.**
4. Check the workflow report, row_count, issuer_count, dates, and independent real-company acceptance test **before** switching any Rosario task to automatic rejection. Actual automation also requires approved private storage/distribution of the weekly registry.

Local commands (Python 3.10+; Python standard library only):

~~~bash
python tase_registry.py refresh --lookback 28
python tase_registry.py stats
python tase_registry.py lookup --corporate-id 512345678 --name "שם חברה"
python tase_registry.py lookup --name "שם חברה"
python -m unittest discover -s tests -p 'test_tase_registry.py' -v
~~~

The refresh command needs TASE_API_KEY set in its **environment**. On GitHub Actions the secret is passed by the workflow. Querying the committed empty file safely returns **לא ניתן לקבוע**.

### Manual fallback without bypass

If the API is blocked, the operator may download the data via an authorized official TASE website export. An issuer-linked securities file is essential; a plain security-name-only list does not support safe corporate-ID matching.

~~~bash
python tase_registry.py refresh-manual --official-source-attested \
  --companies /secure/path/official_companies.csv \
  --securities /secure/path/official_securities_with_issuer_ids.csv \
  --types /secure/path/official_security_types.csv \
  --source-date 2026-11-23
~~~

The manual file is tagged **operator-attested, not independently verified**. Do not claim it was fetched by the API. Its CSV header format must be validated on the actual downloaded file. A filtered export must not be described as full coverage.


## NEWS integration — safe, opt-in sidecar

**Actual NEWS topology (verified on `main` 2026-11-23):** the public repo's daily production path is `.github/workflows/daily-procurement.yml` → `daily_procurement.py` → `procurement_delta.py` → `procurement_events.json`, preserving `state/procurement_versions.json` and compressed procurement baselines. The private Rosario Feeds news scanner and Monday lead tasks are NOT in public NEWS. TASE membership must never alter procurement collection, archive verification, history/baseline, event IDs or existing daily alerts.

**Opt-in post-processing, never an upstream filter:** `tase_procurement_screen.py` consumes an existing procurement event JSON and an authorized, current TASE JSON snapshot, creates a **different** output file `procurement_events_tase_review.json`. It appends an advisory `tase_screen` section to each event with each supplier's listing evidence and `tase_enrichment` root summary. The original events file, event IDs, publication IDs, change counts and event order remain unchanged. The tool has no network, email, GitHub write, Monday call or TASE secret access. Its import has no side effects.

**Supplier mapping:** NEWS `winners` are strings encoded as `"מספר חפ ספק|שם ספק"`; every supplier is evaluated separately. An exact 9-digit corporate-ID match to official traded **shares** can yield an *advisory* positive `all_winners_exact_id_match`; corporate-bond-only matches produce `bond_alert`, never auto-exclusion. A name-only match requires review; mismatched corporate ID versus name requires review; an unlisted/unknown/ambiguous ID does not qualify for exclusion. Multiple winners: the event-level equity-exclusion flag is true **only if every supplier** has a reliable exact-ID match to shares. It never drops events, even when every supplier is listed.

**Fail-open for government procurement, fail-closed for exclusions:** a missing, stale, corrupt or unauthorized TASE registry yields `tase_enrichment.status="unavailable"`, supplier classifications `לא ניתן לקבוע`, and **zero** automatic positive exclusions. The procurement event data still passes through untouched. If the event input itself is malformed, the sidecar exits nonzero without overwriting the old output.

Run locally only against data you are authorized to store and process (NOT in a public GitHub artifact):
```bash
python tase_procurement_screen.py \
  --events procurement_events.json \
  --registry /secure/private/tase_registered_securities.json \
  --output /secure/private/procurement_events_tase_review.json

python -m unittest discover -s tase_tests -p 'test_*.py' -v
```

**Non-interference guardrails:** no changes to `daily_procurement.py`, `procurement_delta.py`, `gov_dataset_reader.py`, government snapshot schemas or published procurement artifacts. The existing `.github/workflows/daily-procurement.yml` has exactly one additive post-processing step in the merged NEWS integration, without changing prior pipeline operations or schedules. The original `tests/` directory is left unchanged; all TASE tests are under `tase_tests/`. The separate TASE CI job runs every existing NEWS test with its usual `lxml==6.0.2`, plus a live shadow event test using ephemeral official data. The TASE stage in the proposed daily workflow runs after procurement events and metadata are produced; it never gates existing procurement jobs, and uses `continue-on-error` with a four-minute step timeout.

**Deployed to NEWS main as a non-blocking shadow stage, not deployed to private Rosario:** the daily workflow's optional shadow step is implemented in this branch, tested separately, and will execute after merge only on runs that find new government procurement events. It calls TASE only for nonempty batches, enriches event data in the ephemeral runner and writes no public company-level TASE artifact. A stable private output storage/transport and licensing review are still required before Rosario's private downstream lead agents can consume this data. No Monday modifications and no private Rosario board hooks exist in NEWS.



### Daily NEWS shadow hook (proposed / unmerged)

`tase_news_integration.py` is called **after** `daily_procurement.py` and its safe source-state save in the GitHub workflow. It checks `procurement_events.json` for new event records, and when none are present it emits `skipped_no_events` without contacting TASE. Otherwise it refreshes an authorized TASE snapshot into `$RUNNER_TEMP/news_tase_registry.json`, produces `$RUNNER_TEMP/news_tase_review.json` containing the same events plus annotations, and logs **aggregate numbers only**. Neither temporary file is uploaded or committed. All original procurement artifacts stay exactly as they were; a TASE failure does not fail the procurement job. The extra stage is limited to four minutes and only runs with the GitHub secret `RNEWS_TASE_2026`. The first post-merge NEWS daily run (45171981064) completed successfully and reported skipped_no_events; it did not fetch the TASE API during that empty batch.

**Real-data validation:** `tase_tests/real_news_baseline_audit.py` samples actual previously published government **tender** winners from committed `state/procurement_snapshots/tenders.json.gz`, then checks those against a freshly fetched official TASE snapshot on the same temporary runner. This is deliberately marked **historical baseline sampling** and is not misreported as new leads. The audit checks that no government event, winner, event ID, or ordering is removed; no name-only match becomes auto-exclusion; and the source remains unmodified. Only aggregate diagnostics are logged.

## Exact post-addition contract — three destinations

Reusable read-only CLI: `tase_company_guard.py`. It accepts `--destination` as `leads`, `watchlist` or `owned_company_watchlist`, plus company name, optional 9-digit corporate ID, and `--registry` pointing to an *authorized private snapshot*. It emits structured `action`:
- `reject_public_equity`: remove/reject the created company record **only after verifying its exact identity**, preserve an audit trace and evidence.
- `keep_with_bond_warning`: keep the record but flag strong negative scoring; the existing Rosario scoring agent determines numeric penalty.
- `manual_review`: missing/stale data, name-only match or conflicting identities.
- `continue_existing_checks`: not found; **not evidence that the company is private**.

This CLI does not talk to Monday and does not itself alter any board or score. Production Rosario integration must be attached to EVERY company-added event (lead, company in monitoring, owned company in monitoring) with idempotency, rollback/audit, and a secure licensed registry consumer. A poller/trigger must cover direct/manual additions as well as scheduled bot insertions. Testing in public NEWS cannot prove Monday event coverage.

```bash
python tase_company_guard.py --registry /secure/tase.json \
  --destination leads --name "חברה לדוגמה" --corporate-id 512345678
```

## Rosario integration contract — NOT wired in this public repository

After each company insertion and before final acceptance in any of the three boards:

~~~python
from tase_registry import lookup
result = lookup(name=candidate_name, corporate_id=candidate_hp)
if result["status"] == "ברשימה" and result["auto_disqualify"]:
    # Reject only confirmed traded shares, include source and last_updated.
    reject_candidate(result)
elif result.get("corporate_bond_confirmed"):
    # Keep candidate but flag strong negative scoring due to known corporate bonds.
    flag_existing_bond_underwriter_relationship_for_review(result)
else:
    # Continue existing checks for ownership, IPO intentions, government bodies.
    # Log registry unavailability if status == "לא ניתן לקבוע".
    # Request review if requires_review == True.
    continue_existing_screening(result)
~~~

Target entrypoints: Saturday-night lead research, Tuesday watchlist additions, BDI promotions, new news scanner candidates, and any flow adding to the "חברות בבעלות" board. Their exact file/task names and call locations must be checked against the **current private Rosario CLAUDE.md**; it is not part of NEWS. The TASE module does not modify Monday.

Other Rosario exclusions (subsidiaries >50% owned by public companies, IPO plans, government/municipal companies) **remain in the existing research workflow**. The TASE file checks none of these. A recipient must load the current JSON with metadata and apply freshness on each lookup.

## Acceptance / readiness

- [x] Unit tests: 10 synthetic positives (shares, bonds, both), 10 synthetic negatives, mismatched ID/name, similar names, stale/missing/corrupt file, unknown classification, blocked API behavior.
- [x] Missing key -> failed status, no fabricated companies, last successful snapshot preserved after subsequent failures.
- [x] First real authenticated TASE fetch succeeded on 2026-11-23: 693 official companies, 2,256 observed securities, 1,505 correctly classified share/bond rows, 661 linked issuers; source as of 2026-11-20 (read-only workflow).
- [x] Independent live acceptance PASS: 17/17 known TASE-listed corporate IDs matched without ambiguity (including 2/2 bond-only), 10 synthetic negatives not auto-rejected, name-only forced review, stale data fails closed; run 45150020864 on 2026-11-23.
- [ ] Ten **real** Rosario-watchlist private companies checked confidentially; not placed in NEWS.
- [ ] Confirm coverage of suspended and illiquid securities, or retain caveat.
- [ ] After manual merge, training agent confirms actual task usage; document results.

## Security and system log

No third-party packages; no execution of downloaded ZIPs, shell commands, Selenium, or Monday writes. Raw API responses and complete registry rows must **not** be committed or published in this public repository without confirming licensing/redistribution rights. Use only authorized internal storage for private operational data. API origin/endpoint allowlisted; redirects refused; size limits, response validation and atomic data file updates. Data older than ten days returns **לא ניתן לקבוע**, even when the last failed attempt is recent. A failed refresh keeps the last known-good rows but sets run_status=failed.

**System change log — November 23, 2026:** branch adds a standalone official-source exclusion registry, offline tests, failed-state placeholder JSON and Friday workflow. Live TASE response validated, but no persistent production rows or public raw-data uploads; no changes to Rosario private tasks, no Monday access; NEWS main merge completed as 17b8898. Public NEWS must not contain private Rosario records or restricted TASE data whose redistribution is not authorized.

## License-aware output behavior

The official site cautions against redistribution of TASE raw files without prior authorization: https://www.tase.co.il/en/support-page/?questionCode=nav205 . Do not assume a DataWise subscription permits publishing API output in a public GitHub repo. The weekly workflow therefore retains the validated JSON only inside the ephemeral GitHub runner, prints aggregate status/acceptance metrics, and discards the raw data when the job ends. Nothing writes to public main. An explicitly approved private storage and consumer path is still required for live Rosario lead exclusions. The checked-in zero-row placeholder always fails closed.
