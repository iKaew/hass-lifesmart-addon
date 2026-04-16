#!/usr/bin/env python3
"""Dump LifeSmart AC profile IR codes for debugging."""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.lifesmart.const import (  # noqa: E402
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
)
from custom_components.lifesmart.lifesmart_client import LifeSmartClient  # noqa: E402


def parse_csv_ints(value: str) -> list[int]:
    """Parse comma-separated ints and ranges like 16-30."""
    result: list[int] = []
    for chunk in value.split(","):
        item = chunk.strip()
        if not item:
            continue
        if "-" in item:
            start_str, end_str = item.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            step = 1 if end >= start else -1
            result.extend(range(start, end + step, step))
        else:
            result.append(int(item))
    return result


def sanitize_filename(value: str) -> str:
    """Make a string safe for filenames."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def load_lifesmart_entry(config_dir: Path) -> dict:
    """Load the first LifeSmart config entry from Home Assistant storage."""
    storage_file = config_dir / ".storage" / "core.config_entries"
    data = json.loads(storage_file.read_text(encoding="utf-8"))
    for entry in data.get("data", {}).get("entries", []):
        if entry.get("domain") == "lifesmart":
            merged = dict(entry.get("data", {}))
            merged.update(entry.get("options", {}))
            return merged
    raise RuntimeError(f"No LifeSmart config entry found in {storage_file}")


async def dump_codes(args: argparse.Namespace) -> Path:
    """Fetch AC codes and write them to a JSON file."""
    entry = load_lifesmart_entry(args.config_dir)
    client = LifeSmartClient(
        args.region or entry.get("region", ""),
        entry[CONF_LIFESMART_APPKEY],
        entry[CONF_LIFESMART_APPTOKEN],
        entry[CONF_LIFESMART_USERID],
        entry[CONF_LIFESMART_USERPASSWORD],
    )

    login = await client.login_async()
    if login.get("code") != "success":
        raise RuntimeError(f"LifeSmart login failed: {login}")

    payload = {
        "brand": args.brand,
        "category": args.category,
        "idx": args.idx,
        "generated_at": datetime.now(UTC).isoformat(),
        "dimensions": {
            "keys": args.keys,
            "powers": args.powers,
            "modes": args.modes,
            "temps": args.temps,
            "winds": args.winds,
            "swings": args.swings,
        },
        "results": [],
    }

    combos = itertools.product(
        args.keys,
        args.powers,
        args.modes,
        args.temps,
        args.winds,
        args.swings,
    )

    total = (
        len(args.keys)
        * len(args.powers)
        * len(args.modes)
        * len(args.temps)
        * len(args.winds)
        * len(args.swings)
    )
    print(f"Fetching {total} combinations for {args.brand} idx={args.idx}...")

    for i, (key, power, mode, temp, wind, swing) in enumerate(combos, start=1):
        response = await client.get_ac_codes_async(
            category=args.category,
            brand=args.brand,
            idx=args.idx,
            key=key,
            power=power,
            mode=mode,
            temp=temp,
            wind=wind,
            swing=swing,
        )
        payload["results"].append(
            {
                "key": key,
                "power": power,
                "mode": mode,
                "temp": temp,
                "wind": wind,
                "swing": swing,
                "response": response,
            }
        )
        if i % 25 == 0 or i == total:
            print(f"  {i}/{total}")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_name = (
        f"ac_profile_{sanitize_filename(args.brand)}_{sanitize_filename(args.idx)}"
        f"_{timestamp}.json"
    )
    output_path = args.output or (args.config_dir / default_name)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Dump LifeSmart AC profile codes via GetACCodes."
    )
    parser.add_argument("--brand", required=True, help="AC brand name")
    parser.add_argument("--idx", required=True, help="AC profile index")
    parser.add_argument(
        "--category", default="ac", help="IR category, default: ac"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=ROOT / "config",
        help="Home Assistant config directory, default: ./config",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Override region instead of reading it from config entry",
    )
    parser.add_argument(
        "--keys",
        default="power",
        help="Comma-separated key operations, e.g. power or power,mode,temp",
    )
    parser.add_argument(
        "--powers",
        default="0,1",
        help="Comma-separated powers/ranges, default: 0,1",
    )
    parser.add_argument(
        "--modes",
        default="0-4",
        help="Comma-separated modes/ranges, default: 0-4",
    )
    parser.add_argument(
        "--temps",
        default="16-30",
        help="Comma-separated temps/ranges, default: 16-30",
    )
    parser.add_argument(
        "--winds",
        default="0-3",
        help="Comma-separated winds/ranges, default: 0-3",
    )
    parser.add_argument(
        "--swings",
        default="0-4",
        help="Comma-separated swings/ranges, default: 0-4",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output JSON path",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.keys = [item.strip() for item in args.keys.split(",") if item.strip()]
    args.powers = parse_csv_ints(args.powers)
    args.modes = parse_csv_ints(args.modes)
    args.temps = parse_csv_ints(args.temps)
    args.winds = parse_csv_ints(args.winds)
    args.swings = parse_csv_ints(args.swings)

    try:
        output_path = asyncio.run(dump_codes(args))
    except Exception as err:  # noqa: BLE001
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(f"Wrote AC profile dump to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
