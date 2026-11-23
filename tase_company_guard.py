#!/usr/bin/env python3
"""Post-addition TASE safety gate for three Rosario company-entry paths.

This module does not make Monday calls, change scores, or remove existing leads.
Private production workflow supplies the candidate and authorized local TASE registry.
"""
import argparse
import json
from pathlib import Path
import sys
from tase_registry import lookup


ALLOWED_DESTINATIONS = frozenset((
    "leads", "watchlist", "owned_company_watchlist"
))


def check(company_name, corporate_id, destination, *, registry):
    if destination not in ALLOWED_DESTINATIONS:
        raise ValueError("Unknown company-entry destination")
    decision = lookup(Path(registry), name=company_name, corporate_id=corporate_id)
    confirmed_equity = bool(decision.get("equity_listed_confirmed"))
    confirmed_bonds = bool(decision.get("corporate_bond_confirmed"))
    # Production writes/records only after its independent existing checks.
    action = (
        "reject_public_equity" if confirmed_equity else
        "keep_with_bond_warning" if confirmed_bonds else
        "manual_review" if decision.get("requires_review") or
                           decision.get("status") == "לא ניתן לקבוע" else
        "continue_existing_checks"
    )
    return {
        "destination": destination,
        "action": action,
        "reject": confirmed_equity,
        "bond_warning": confirmed_bonds,
        "score_signal": "strong_negative" if confirmed_bonds else None,
        "status": decision.get("status"),
        "type": decision.get("type"),
        "requires_review": bool(decision.get("requires_review")),
        "reason": decision.get("reason"),
        "source": decision.get("source"),
        "last_updated": decision.get("last_updated"),
        "evidence": {
            "match_method": decision.get("match_method"),
            "security_ids": decision.get("security_ids", []) if confirmed_equity or confirmed_bonds else [],
            "bond_series": decision.get("bond_series", []) if confirmed_bonds else [],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Post-addition TASE screening (read-only)")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--destination", choices=sorted(ALLOWED_DESTINATIONS), required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--corporate-id", default="")
    args = parser.parse_args(argv)
    output = check(args.name, args.corporate_id, args.destination, registry=args.registry)
    print(json.dumps(output, ensure_ascii=False))
    # A listed equity yields a structured decision, never an automation crash.
    return 0


if __name__ == "__main__":
    sys.exit(main())
