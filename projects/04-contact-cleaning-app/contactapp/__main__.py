"""python3 -m contactapp [--port 8770] [--crm-env-file PATH] [--allow-crm-push]"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .app import Config
from .envfile import read_keys
from .server import serve


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="contactapp")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 for a public deployment (no CRM token allowed there)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8770")))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--crm-env-file", type=Path, help="an .env file; only HUBSPOT_TOKEN and HUBSPOT_PORTAL_ID are read from it")
    ap.add_argument("--allow-crm-push", action="store_true", help="enable the real push to HubSpot (off by default: preview only)")
    args = ap.parse_args(argv)
    token = portal = ""
    if args.crm_env_file:
        try:
            keys = read_keys(args.crm_env_file, ("HUBSPOT_TOKEN", "HUBSPOT_PORTAL_ID"))
        except OSError as exc:
            sys.exit(f"Cannot read {args.crm_env_file}: {exc.strerror}")
        token, portal = keys.get("HUBSPOT_TOKEN", ""), keys.get("HUBSPOT_PORTAL_ID", "")
        if not token:
            sys.exit("HUBSPOT_TOKEN was not found in that file.")
    if args.allow_crm_push and not token:
        sys.exit("--allow-crm-push needs --crm-env-file with a HUBSPOT_TOKEN.")
    serve(Config(allowed_hosts=(), crm_token=token, expected_portal=portal, allow_push=args.allow_crm_push), args.host, args.port,
          not args.no_browser)


if __name__ == "__main__":
    main()
