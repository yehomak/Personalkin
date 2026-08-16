#!/usr/bin/env python3
"""
Personalkin setup — run after garmin-sync is already set up.

  python setup.py

Installs dependencies, configures macOS notifications, adds the `ci`
terminal alias, and prints the MCP config snippet for Claude Code.

Prerequisite: run `python setup.py` in garmin-sync first.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PERSONALKIN   = Path(__file__).parent
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def ok(msg):   print(f"  ✓ {msg}")
def info(msg): print(f"  · {msg}")
def warn(msg): print(f"  ⚠ {msg}")
def step(n, total, title): print(f"\n[{n}/{total}] {title}")
def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default


def run(cmd, cwd=None, capture=True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "command failed")
    return result.stdout.strip()


def python_in(venv: Path) -> str:
    return str(venv / "bin" / "python")


# ── step 1: garmin-sync path ──────────────────────────────────────────────────

def confirm_garmin_sync() -> Path:
    default = os.environ.get("GARMIN_SYNC", str(Path.home() / "Projects/garmin-sync"))
    raw = ask("Path to garmin-sync repo", default)
    path = Path(raw).expanduser()
    if not (path / "garmin.duckdb").exists():
        warn(f"garmin.duckdb not found at {path}")
        warn("Run `python setup.py` in garmin-sync first, then come back.")
        if ask("Continue anyway?", "n").lower() != "y":
            sys.exit(1)
    else:
        ok(f"garmin-sync at {path}")
    return path


# ── step 2: personalkin deps ──────────────────────────────────────────────────

def install_deps():
    venv = PERSONALKIN / ".venv"
    if not venv.exists():
        info("Creating .venv...")
        run([sys.executable, "-m", "venv", str(venv)])
    info("Installing requirements...")
    run([python_in(venv), "-m", "pip", "install", "-q", "-r",
         str(PERSONALKIN / "requirements.txt")])
    ok("dependencies ready")


# ── step 3: macOS notifications ───────────────────────────────────────────────

DAILY_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.personalkin.daily</string>
    <key>ProgramArguments</key><array>
        <string>{python}</string>
        <string>{script}</string>
    </array>
    <key>EnvironmentVariables</key><dict>
        <key>GARMIN_SYNC</key><string>{garmin_sync}</string>
    </dict>
    <key>StartCalendarInterval</key><array>
        {weekdays}
    </array>
    <key>StandardOutPath</key><string>/tmp/garmin-daily.log</string>
    <key>StandardErrorPath</key><string>/tmp/garmin-daily.log</string>
</dict></plist>
"""

WEEKDAY_ENTRY = "<dict><key>Weekday</key><integer>{w}</integer><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>"

SIMPLE_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key><array>
        <string>{python}</string>
        <string>{script}</string>
    </array>
    <key>EnvironmentVariables</key><dict>
        <key>GARMIN_SYNC</key><string>{garmin_sync}</string>
    </dict>
    <key>StartCalendarInterval</key><dict>
        {interval}
    </dict>
    <key>StandardOutPath</key><string>/tmp/{log}.log</string>
    <key>StandardErrorPath</key><string>/tmp/{log}.log</string>
</dict></plist>
"""


def setup_notifications(garmin_sync: Path):
    if not shutil.which("terminal-notifier"):
        if shutil.which("brew"):
            info("Installing terminal-notifier...")
            run(["brew", "install", "terminal-notifier"])
            ok("terminal-notifier installed")
        else:
            warn("Homebrew not found — install manually: brew install terminal-notifier")
            return

    time_str = ask("Notification time (HH:MM)", "10:00")
    try:
        h, m = (int(x) for x in time_str.split(":"))
    except (ValueError, TypeError):
        h, m = 10, 0

    py      = python_in(PERSONALKIN / ".venv")
    scripts = PERSONALKIN / "scripts"
    gs      = str(garmin_sync)
    la      = LAUNCH_AGENTS
    la.mkdir(parents=True, exist_ok=True)

    weekdays = "\n        ".join(
        WEEKDAY_ENTRY.format(w=w, h=h, m=m) for w in range(7)
    )
    (la / "com.personalkin.daily.plist").write_text(
        DAILY_PLIST.format(python=py, script=scripts / "run_daily.py",
                           garmin_sync=gs, weekdays=weekdays)
    )
    (la / "com.personalkin.weekly.plist").write_text(
        SIMPLE_PLIST.format(
            label="com.personalkin.weekly", python=py,
            script=scripts / "run_weekly.py", garmin_sync=gs,
            interval=f"<key>Weekday</key><integer>1</integer><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer>",
            log="garmin-weekly",
        )
    )
    (la / "com.personalkin.monthly.plist").write_text(
        SIMPLE_PLIST.format(
            label="com.personalkin.monthly", python=py,
            script=scripts / "run_monthly.py", garmin_sync=gs,
            interval=f"<key>Day</key><integer>1</integer><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer>",
            log="garmin-monthly",
        )
    )

    for label in ["com.personalkin.daily", "com.personalkin.weekly", "com.personalkin.monthly"]:
        plist = la / f"{label}.plist"
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        subprocess.run(["launchctl", "load",   str(plist)], capture_output=True)

    ok(f"3 LaunchAgents loaded (daily + weekly Mon + monthly 1st, at {h:02d}:{m:02d})")


# ── step 4: ci alias ─────────────────────────────────────────────────────────

def setup_alias():
    py     = python_in(PERSONALKIN / ".venv")
    script = PERSONALKIN / "scripts" / "save_checkin.py"
    line   = f"alias ci='{py} {script} --training'"

    zshrc = Path.home() / ".zshrc"
    if zshrc.exists() and "save_checkin" in zshrc.read_text():
        ok("ci alias already in ~/.zshrc")
        return

    if ask("Add 'ci' alias to ~/.zshrc?", "y").lower() == "y":
        with open(zshrc, "a") as f:
            f.write(f"\n# Personalkin — log training without watch\n{line}\n")
        ok("added to ~/.zshrc  (run: source ~/.zshrc)")
    else:
        info(f"Add manually:\n  {line}")


# ── MCP config ────────────────────────────────────────────────────────────────

def show_mcp_config(garmin_sync: Path):
    snippet = {
        "personalkin": {
            "type": "stdio",
            "command": python_in(PERSONALKIN / ".venv"),
            "args": [str(PERSONALKIN / "server.py")],
            "env": {
                "GARMIN_SYNC": str(garmin_sync),
                "GARMIN_DB":   str(garmin_sync / "garmin.duckdb"),
            },
        }
    }
    print()
    print("  Add to ~/.claude.json under \"mcpServers\":")
    print()
    for line in json.dumps(snippet, indent=4).splitlines():
        print(f"  {line}")
    print()
    info("Restart Claude Code after editing ~/.claude.json")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("\nPersonalkin — Setup")
    print("─" * 40)

    TOTAL = 4

    step(1, TOTAL, "Locate garmin-sync")
    garmin_sync = confirm_garmin_sync()

    step(2, TOTAL, "Install dependencies")
    install_deps()

    step(3, TOTAL, "macOS notifications")
    if sys.platform == "darwin":
        setup_notifications(garmin_sync)
    else:
        info("Skipping — macOS only")

    step(4, TOTAL, "Terminal alias (ci)")
    setup_alias()

    print("\n" + "─" * 40)
    print("Setup complete.\n")
    show_mcp_config(garmin_sync)


if __name__ == "__main__":
    main()
