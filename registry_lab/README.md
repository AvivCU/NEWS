# Registry resolver lab

This is an isolated public test prototype. No real registry records, CRM data, manifests, credentials or production state are stored here. There are no cron jobs or production writes. Only synthetic test fixtures are used by CI.

## Run locally

Use Python 3.11+ and the official registry CSV exports (primary first, supplemental second):

```sh
python3 resolver.py build /tmp/registry.sqlite /path/to/main.csv /path/to/append.csv
python3 resolver.py query /tmp/registry.sqlite 'Company name'
python3 -m unittest -v test_registry
```

Supply --expected with the validated count to reject an incomplete build. Invalid checksum rows are counted and excluded. The first CSV wins conflicting metadata; normalized name keys from all inputs remain searchable. SQLite opens read-only. All candidate queries are bounded and parameterized; prefix-based fuzzy search ranks at most 100 candidates and never authorizes writes. Exact name is a lookup result, not proof of identity. Prefix blocking misses first-character typos and undocumented trade names.

## Private deployment contract

Build and validate the real database outside this public repository. Compress it as gzip and upload as a versioned private GitHub Release asset, not a Git commit. Keep a trusted manifest with repo, tag, asset, asset_sha256, db_sha256, db_bytes and count; pin it explicitly. Restore with:

```sh
GH_TOKEN=... python3 storage.py /path/to/manifest.json /tmp/registry.sqlite
```

The restore validates the existing cached DB before use, otherwise downloads the pinned asset with gh, checks both hashes and the schema/count, bounds decompression and replaces atomically. Keep the prior release for rollback. In a private workflow use contents: read, hash-versioned Actions Cache, and run discovery of missing IDs before restoring any asset. Skip the resolver if the registry is unavailable. Do not introduce dependencies into existing jobs. This prototype does not implement live Monday discovery/writes, cache action wiring, scheduled registry refresh or public release uploads. Those require private integration and acceptance tests.
