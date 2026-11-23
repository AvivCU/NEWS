# NEWS / Rosario — מאגר פסילה TASE

**Status (2026-11-23): REVIEW REQUIRED.** The read-only GitHub smoke test successfully fetched and parsed live official TASE API responses using the new credential; the PR remains unmerged and no official snapshot has been committed. The committed JSON intentionally contains **zero companies**, with run_status=failed. The real-data smoke test has successfully built the registry, but the snapshot intentionally stays **temporary inside GitHub Actions**. The committed placeholder is not a working production exclusion list. An approved private distribution/storage mechanism must be chosen before Rosario agents can consume it.

## What the module does

One public data file: **data/latest/tase_registered_securities.json** (root metadata plus rows). Each row has the Hebrew/English company names, corporate ID (ח.פ.), issuer ID, company-wide type (מניה / אג"ח / שניהם), security type, security number, security name, ISIN, observation date, update date and official TASE links. The file root includes last_updated, source_as_of, row_count, run_status (success/failed), last_attempt_at, last_error and coverage diagnostics.

| Lookup outcome | Required downstream action |
| --- | --- |
| **ברשימה**, auto_disqualify=true | Exclude immediately with reason "נפסלה – ציבורית/אג"ח"; cite registry URL, security IDs and last_updated; save a web search |
| **ברשימה**, auto_disqualify=false | Name-only match or contradictory identifiers: manual verification; never automatic exclusion |
| **לא ברשימה** | Continue existing public/private checks; NOT proof of a private company |
| **לא ניתן לקבוע** | File missing, corrupt, older than ten days, source data stale or never fetched; continue existing checks and include an unavailable warning in the scan report |

Only an unambiguous exact 9-digit corporate-ID match can authorize auto-disqualification. Exact normalized names can return matches but require review. Similar/fuzzy names never auto-disqualify. If the input company name conflicts with a matching ID, review is required.

## Official sources and crucial limitation

Automated source is TASE **Data Hub / DataWise Securities - Basic**, strictly these GET routes:

- https://datawise.tase.co.il/v1/basic-securities/companies-list
- https://datawise.tase.co.il/v1/basic-securities/securities-types
- https://datawise.tase.co.il/v1/basic-securities/trade-securities-list/{year}/{month}/{day}

Developer portal: https://datahubapi.tase.co.il

Official site references:
- https://market.tase.co.il/he/market_data/tase-companies/public
- https://market.tase.co.il/he/market_data/securities/info/all?cl1=0&dType=1

**Important:** The date-based trade list is a union of recently *traded* securities, not a complete list of all *registered* securities. It can establish reliable issuer-linked **positives** but does not prove a company has no bonds/shares, particularly suspended or illiquid securities. Do not upgrade the coverage to exhaustive without verifying a full official active-listing export or endpoint. No fake source results are created.

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

## Rosario integration contract — NOT wired in this public repository

Before every web lookup and before candidate insertion:

~~~python
from tase_registry import lookup
result = lookup(name=candidate_name, corporate_id=candidate_hp)
if result["status"] == "ברשימה" and result["auto_disqualify"]:
    # Reject: public shares / corporate bond, include source and last_updated.
    reject_candidate(result)
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
- [x] First real authenticated TASE fetch succeeded on 2026-11-23: 693 official companies, 2,256 observed securities, 1,563 classified rows, 663 linked issuers; source as of 2026-11-20 (read-only workflow).
- [ ] Independent real listed-company and bond-only checks added to read-only smoke test; mark verified only after successful live run.
- [ ] Ten **real** Rosario-watchlist private companies checked confidentially; not placed in NEWS.
- [ ] Confirm coverage of suspended and illiquid securities, or retain caveat.
- [ ] After manual merge, training agent confirms actual task usage; document results.

## Security and system log

No third-party packages; no execution of downloaded ZIPs, shell commands, Selenium, or Monday writes. Raw API responses and complete registry rows must **not** be committed or published in this public repository without confirming licensing/redistribution rights. Use only authorized internal storage for private operational data. API origin/endpoint allowlisted; redirects refused; size limits, response validation and atomic data file updates. Data older than ten days returns **לא ניתן לקבוע**, even when the last failed attempt is recent. A failed refresh keeps the last known-good rows but sets run_status=failed.

**System change log — November 23, 2026:** branch adds a standalone official-source exclusion registry, offline tests, failed-state placeholder JSON and Friday workflow. Live TASE response validated, but no persistent production rows or public raw-data uploads; no changes to Rosario private tasks, no Monday access, and no main-branch merge performed. Public NEWS must not contain private Rosario records or restricted TASE data whose redistribution is not authorized.

## License-aware output behavior

The official site cautions against redistribution of TASE raw files without prior authorization: https://www.tase.co.il/en/support-page/?questionCode=nav205 . Do not assume a DataWise subscription permits publishing API output in a public GitHub repo. The weekly workflow therefore retains the validated JSON only inside the ephemeral GitHub runner, prints aggregate status/acceptance metrics, and discards the raw data when the job ends. Nothing writes to public main. An explicitly approved private storage and consumer path is still required for live Rosario lead exclusions. The checked-in zero-row placeholder always fails closed.
