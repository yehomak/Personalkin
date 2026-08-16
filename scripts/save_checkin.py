#!/usr/bin/env python3
"""
Save or update today's check-in.

  save_checkin.py "4 3"            # mood=4, energy=3
  save_checkin.py "4 3 MMA 90min"  # + training
  save_checkin.py --training "MMA 90min"   # update training only (ci alias)
  save_checkin.py --date 2026-08-15 "4 3"  # specific date
"""

import argparse
import sys
from datetime import date
from pathlib import Path

CHECKINS_DIR = Path(__file__).parent.parent / "context" / "health" / "checkins"


def _read(path):
    if not path.exists():
        return {}, ""
    parts = path.read_text().split("---")
    if len(parts) < 2:
        return {}, ""
    fields = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            v = v.split("#")[0].strip()
            if v:
                fields[k.strip()] = v
    notes = parts[2].strip() if len(parts) >= 3 else ""
    return fields, notes


def _write(path, fields, notes=""):
    order = ["mood", "energy", "training"]
    lines = ["---"]
    for k in order:
        if fields.get(k):
            lines.append(f"{k}: {fields[k]}")
    for k, v in fields.items():
        if k not in order and v:
            lines.append(f"{k}: {v}")
    lines.append("---")
    if notes:
        lines.append("")
        lines.append(notes)
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="'mood energy [training]' e.g. '4 3' or '4 3 MMA 90min'")
    parser.add_argument("--training", "-t", help="Update training only")
    parser.add_argument("--date", "-d", help="Date YYYY-MM-DD, default: today")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    CHECKINS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKINS_DIR / f"{target}.md"
    fields, notes = _read(path)

    if args.training:
        fields["training"] = args.training.strip()
        _write(path, fields, notes)
        print(f"✓ {target}  training: {fields['training']}")
        return

    if args.input:
        parts = args.input.strip().split(None, 2)
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            print("Expected 'mood energy' e.g. '4 3' or '4 3 MMA 90min'", file=sys.stderr)
            sys.exit(1)
        fields["mood"] = parts[0]
        fields["energy"] = parts[1]
        if len(parts) > 2:
            fields["training"] = parts[2]
        _write(path, fields, notes)
        summary = f"mood:{fields['mood']}  energy:{fields['energy']}"
        if fields.get("training"):
            summary += f"  training:{fields['training']}"
        print(f"✓ {target}  {summary}")
        return

    print("Usage: save_checkin.py '4 3' or save_checkin.py --training 'MMA 90min'", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
