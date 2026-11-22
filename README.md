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
- The latest listed government tenders and exemptions ZIPs are both labeled **01-11-2026**. Their **contents have not yet been fully parsed for 2025/2026 coverage**.
- First daily monitor run validated both ZIPs (~2.4 MB and ~26.3 MB compressed).
- Second daily monitor run showed both `unchanged`: **1 page request, 0 ZIP downloads**.
- Full historical CKAN scan: **363,768 records across five datasets**, all completed. These are *not* the newly published monthly XLS files.
- This is **not** deployed into the private Rosario Feeds production repository or Monday.com.

## Operational limits
- GitHub scheduled workflows may run late and are not guaranteed to start at the exact minute.
- The tracker considers a changed published URL a new version. If a file's bytes change at the same URL, the lightweight daily check will not detect it; periodic forced validation can catch this.
- Publication date and reporting period are distinct: verify actual row dates before creating 2025/2026 business leads.
