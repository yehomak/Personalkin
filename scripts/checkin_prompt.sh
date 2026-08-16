#!/usr/bin/env bash
# Triggered by the daily notification's -execute handler.
# Shows a macOS dialog, saves result to today's check-in file.
#
# Dialog expects: "4 3" (mood energy) or "4 3 MMA 90min" (+ training)

PYTHON="$HOME/Projects/Personalkin/.venv/bin/python"
SCRIPT="$HOME/Projects/Personalkin/scripts/save_checkin.py"

result=$(osascript \
  -e 'set msg to "Mood · Energy  (e.g. \"4 3\")" & return & "With training:  \"4 3 MMA 90min\""' \
  -e 'set r to text returned of (display dialog msg default answer "" with title "How do you feel today?" buttons {"Cancel", "Save"} default button "Save")' \
  -e 'return r' \
  2>/dev/null) || exit 0

result="$(echo "$result" | xargs 2>/dev/null)"
[[ -z "$result" ]] && exit 0

"$PYTHON" "$SCRIPT" "$result"
