import argparse
import json
import logging

from .airtable import AirtableClient
from .config import get_settings
from .service import SearchService


def main() -> None:
    parser = argparse.ArgumentParser(prog="scheme_b2b")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-once")
    run.add_argument("--manual", action="store_true")

    sub.add_parser("dispatch-outbox")

    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    service = SearchService(settings, AirtableClient(settings))
    result = (
        service.run_once(manual=args.manual)
        if args.command == "run-once"
        else service.dispatch_outbox()
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
