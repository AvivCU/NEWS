# Rosario — public official-source monitoring (test repository)

This public repository contains **no private Rosario watchlists, Monday data or credentials**.

## Daily government procurement monitor
- Workflow: [Daily government procurement update](https://github.com/AvivCU/NEWS/actions/workflows/daily-procurement.yml)
- Schedule: every day at **06:37 UTC** (08:37 Israel winter / 09:37 Israel summer).
- Reads the official [Government Procurement Administration reports page](https://mr.gov.il/ilgstorefront/he/news/details/230920201036) and extracts the published versioned **Tenders** and **Exemptions** ZIP links including their `context` parameters.
- Tracks the newest verified URLs, original sizes, SHA-256 and first-observed timestamps in [state/procurement_versions.json](state/procurement_versions.json).
- **On an unchanged day:** one page request, zero ZIP downloads, no git change.
- **On a changed version:** page request + one ZIP fetch for each new/changed archive, ZIP integrity verification and state update. The original XLS files are *not* committed to this public repository.
- Uploads a public lightweight `procurement_daily_report.json` as a 14-day Actions artifact; failures do not overwrite known-good state.
- Manual Run workflow option `force_download` validates the archive again (generates additional requests).

## Other verification workflows
- **Official sources access audit:** 10 source endpoints plus CKAN metadata and record sampling.
- **Live government procurement monthly exports:** forces a real download and ZIP inspection (not daily).
- **Full official datasets scan:** full pagination across five historical/annual CKAN resources. This scan is manual/push-triggered only, *not* scheduled daily.

### Verified on 2026-11-22
- The latest listed government tenders and exemptions ZIPs are both labeled **01-11-2026**. Their contents were parsed to create a publication-level baseline; the year-by-year breakdown within these exports was not measured.
- First daily monitor run validated both ZIPs (~2.4 MB and ~26.3 MB compressed).
- Second daily monitor run showed both `unchanged`: **1 page request, 0 ZIP downloads**.
- Full historical CKAN scan: **363,768 records across five datasets**, all completed. These are *not* the newly published monthly XLS files.
- This is **not** deployed into the private Rosario Feeds production repository or Monday.com.

## Operational limits
- GitHub scheduled workflows may run late and are not guaranteed to start at the exact minute.
- The tracker considers a changed published URL a new version. If a file's bytes change at the same URL, the lightweight daily check will not detect it; periodic forced validation can catch this.
- Publication date and reporting period are distinct: verify actual row dates before creating 2025/2026 business leads.

## Publication-level change detection (implemented and tested)
- Reader: [procurement_delta.py](procurement_delta.py) streams the government's mislabeled `.xls` files (XML Spreadsheet 2003), with strict publication-id validation.
- The source contains `מספר פרסום`, `סטטוס`, `שם ספק זוכה` (tenders), `שם ספק` (exemptions), `מספר חפ ספק` and relevant dates. Groups all rows sharing one publication ID to avoid confusing multi-supplier publications with new tenders.
- Snapshot baseline: `state/procurement_snapshots/{tenders,exemptions}.json.gz` is committed after successful archive verification. No giant Excel file is committed.
- On a new archive it classifies `new_publication`, `winner_assigned`, `winner_changed`, `status_changed`, and `details_changed`, and counts removed publication IDs separately. Update-date-only changes are ignored.
- **First import is baseline-only** and produces **zero historical new-event alerts**. Verified baseline from the November 2026 files: 24,892 tender rows / 22,290 publication IDs, and 241,584 exemption rows / 212,302 publication IDs.
- Later events are exported to the `procurement_events.json` Action artifact; the report includes counts and up to 250 recent entries (publication date within 120 days).
- Unchanged daily run: no ZIP download and no event emission. Synthetic tests cover new tenders, first winner, changed status, and unchanged update-only dates.
- **Every Sunday on the scheduled run,** force-download and compare file hashes, so updates to an existing URL can also be detected. This is *one* weekly expensive validation, not a daily re-download.
- Source metadata and both snapshots are committed only when archive download and parsing both succeed; the old baseline is retained on failure.
- Does **not** yet write leads to private Rosario Monday boards, assess company private ownership/revenue, or replace its existing production scrapers. Events in `NEWS` are ready for integration.

## Fixes for older tenders and material contract changes — 2026-11-22
- **Old tender, newly awarded:** Changes to an existing publication are treated as newly observed events regardless of the original tender publication date. The event includes `detected_utc`, original `published`, and `source_updated`.
- New publication IDs with historic original dates are explicitly tagged `historical_backfill` for downstream review instead of being silently discarded.
- **Contract economics:** `amount_changed` and `period_changed` are compared using structured `היקף כספי`, `מטבע`, `תאריך תחילת תקופת התקשרות`, and `תאריך סיום תקופת התקשרות`. Dates and numeric formats are normalized to avoid false financial flags from formatting alone.
- Routine technical/metadata edits stay `details_changed` and do not produce business event alerts.
- Existing snapshot version 1 auto-migrates to version 2 on one verified reread of the official current archive. No artificial change alerts are generated by migration. A legacy snapshot cannot reconstruct old amount history; complete financial comparisons begin after that migration.
- The event limit is raised to 10,000 **with fail-safe refusal to advance state** if exceeded, instead of silently dropping changes.
- Unit tests exercise old-tender newly assigned winners, amount increases, contract extensions, formatting-only edits, legacy migration and unchanged re-runs. Actual future monthly-version differences have not yet occurred, so real new event precision remains to be validated.
- Production Rosario Feeds and private Monday boards remain unchanged.
