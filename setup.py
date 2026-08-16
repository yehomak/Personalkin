#!/usr/bin/env python3
"""
Personalkin setup — run once after cloning.

  python setup.py

Walks through: dependencies → Garmin auth → initial sync →
physiology profile → macOS notifications → terminal alias → MCP config.
Safe to re-run; skips steps already done.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PERSONALKIN = Path(__file__).parent
GARMIN_SYNC = Path(os.environ.get("GARMIN_SYNC", PERSONALKIN.parent / "garmin-sync"))
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


# ── helpers ───────────────────────────────────────────────────────────────────

def ok(msg):  print(f"  ✓ {msg}")
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
        raise RuntimeError((result.stderr or result.stdout or "").strip().splitlines()[-1] if
                           (result.stderr or result.stdout) else "command failed")
    return result.stdout.strip()


def python_in(venv: Path) -> str:
    return str(venv / "bin" / "python")


# ── step 1: garmin-sync path ──────────────────────────────────────────────────

def confirm_garmin_sync() -> Path:
    if not GARMIN_SYNC.exists():
        p = ask(f"garmin-sync path (not found at {GARMIN_SYNC})")
        path = Path(p).expanduser()
        if not path.exists():
            print(f"  Error: {path} does not exist. Clone garmin-sync first.")
            sys.exit(1)
        return path
    ok(f"garmin-sync at {GARMIN_SYNC}")
    return GARMIN_SYNC


# ── step 2: dependencies ──────────────────────────────────────────────────────

def install_deps(garmin_sync: Path):
    for label, repo, reqs in [
        ("garmin-sync", garmin_sync, garmin_sync / "requirements.txt"),
        ("personalkin",  PERSONALKIN,  PERSONALKIN / "requirements.txt"),
    ]:
        venv = repo / ".venv"
        if not venv.exists():
            info(f"Creating .venv in {label}...")
            run([sys.executable, "-m", "venv", str(venv)])
        info(f"Installing {label} requirements...")
        run([python_in(venv), "-m", "pip", "install", "-q", "-r", str(reqs)])
        ok(label)


# ── step 3: garmin auth ───────────────────────────────────────────────────────

def garmin_auth(garmin_sync: Path):
    env_file = garmin_sync / ".env"
    garth    = garmin_sync / ".garth" / "garmin_tokens.json"

    if garth.exists():
        ok("Garmin session already cached (.garth/)")
        return

    if not env_file.exists():
        print()
        email    = ask("Garmin email")
        password = ask("Garmin password")
        env_file.write_text(f"GARMIN_EMAIL={email}\nGARMIN_PASSWORD={password}\n")
        ok(".env written")
    else:
        ok(".env found")

    info("Authenticating...")
    try:
        run([python_in(garmin_sync / ".venv"), "auth.py"], cwd=garmin_sync)
        ok("Authenticated")
    except RuntimeError as e:
        warn(f"Auth failed: {e}")
        warn("Try running:  cd garmin-sync && .venv/bin/python auth_interactive.py")
        if ask("Continue setup anyway?", "y").lower() != "y":
            sys.exit(1)


# ── step 4: initial sync ──────────────────────────────────────────────────────

def initial_sync(garmin_sync: Path):
    db = garmin_sync / "garmin.duckdb"
    if db.exists():
        ok(f"Database exists ({db.stat().st_size // 1024} KB) — skipping backfill")
        return

    days = ask("Days to backfill", "30")
    try:
        days = int(days)
    except ValueError:
        days = 30

    info(f"Syncing {days} days (this takes a minute)...")
    run([python_in(garmin_sync / ".venv"), "sync.py", "--backfill", str(days)],
        cwd=garmin_sync, capture=False)
    ok(f"{days}-day backfill done")


# ── step 5: physiology profile ────────────────────────────────────────────────

def fetch_physiology(garmin_sync: Path):
    output = PERSONALKIN / "context" / "health" / "physiology.json"
    if output.exists():
        ok("physiology.json already exists — skipping")
        return
    info("Fetching from Garmin API...")
    env = {**os.environ, "GARMIN_SYNC": str(garmin_sync)}
    try:
        subprocess.run(
            [python_in(PERSONALKIN / ".venv"), "scripts/fetch_physiology.py"],
            cwd=PERSONALKIN, env=env, check=True,
        )
    except subprocess.CalledProcessError as e:
        warn(f"Physiology fetch failed: {e}")


# ── step 6: macOS notifications ───────────────────────────────────────────────

DAILY_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.personalkin.daily</string>
    <key>ProgramArguments</key><array>
        <string>{python}</string>
        <string>{script}</string>
    </array>
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
    <key>StartCalendarInterval</key><dict>
        {interval}
    </dict>
    <key>StandardOutPath</key><string>/tmp/{log}.log</string>
    <key>StandardErrorPath</key><string>/tmp/{log}.log</string>
</dict></plist>
"""


def setup_notifications():
    if not shutil.which("terminal-notifier"):
        if shutil.which("brew"):
            info("Installing terminal-notifier...")
            run(["brew", "install", "terminal-notifier"])
            ok("terminal-notifier installed")
        else:
            warn("Homebrew not found. Install terminal-notifier manually: brew install terminal-notifier")
            return

    time_str = ask("Notification time (HH:MM)", "10:00")
    try:
        h, m = (int(x) for x in time_str.split(":"))
    except (ValueError, TypeError):
        h, m = 10, 0

    python    = python_in(PERSONALKIN / ".venv")
    scripts   = PERSONALKIN / "scripts"
    la        = LAUNCH_AGENTS
    la.mkdir(parents=True, exist_ok=True)

    # Daily (every day)
    weekdays = "\n        ".join(WEEKDAY_ENTRY.format(w=w, h=h, m=m) for w in range(7))
    daily_content = DAILY_PLIST.format(
        python=python, script=scripts / "run_daily.py", weekdays=weekdays
    )
    (la / "com.personalkin.daily.plist").write_text(daily_content)

    # Weekly (Monday)
    weekly_content = SIMPLE_PLIST.format(
        label="com.personalkin.weekly", python=python,
        script=scripts / "run_weekly.py",
        interval=f"<key>Weekday</key><integer>1</integer><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer>",
        log="garmin-weekly",
    )
    (la / "com.personalkin.weekly.plist").write_text(weekly_content)

    # Monthly (1st of month)
    monthly_content = SIMPLE_PLIST.format(
        label="com.personalkin.monthly", python=python,
        script=scripts / "run_monthly.py",
        interval=f"<key>Day</key><integer>1</integer><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer>",
        log="garmin-monthly",
    )
    (la / "com.personalkin.monthly.plist").write_text(monthly_content)

    # Load / reload
    for label in ["com.personalkin.daily", "com.personalkin.weekly", "com.personalkin.monthly"]:
        plist = la / f"{label}.plist"
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        subprocess.run(["launchctl", "load",   str(plist)], capture_output=True)

    ok(f"3 LaunchAgents loaded (daily + weekly Mon + monthly 1st, at {h:02d}:{m:02d})")


# ── step 7: ci alias ─────────────────────────────────────────────────────────

def setup_alias():
    python = python_in(PERSONALKIN / ".venv")
    script = PERSONALKIN / "scripts" / "save_checkin.py"
    alias_line = f"alias ci='{python} {script} --training'"

    zshrc = Path.home() / ".zshrc"
    if zshrc.exists() and "save_checkin" in zshrc.read_text():
        ok("ci alias already in .zshrc")
        return

    if ask("Add 'ci' alias to ~/.zshrc?", "y").lower() == "y":
        with open(zshrc, "a") as f:
            f.write(f"\n# Personalkin — log training without watch\n{alias_line}\n")
        ok("Added to ~/.zshrc  (run: source ~/.zshrc)")
    else:
        info(f"Add manually to ~/.zshrc:\n  {alias_line}")


# ── step 8: MCP config ────────────────────────────────────────────────────────

def show_mcp_config(garmin_sync: Path):
    python  = python_in(PERSONALKIN / ".venv")
    snippet = {
        "personalkin": {
            "type": "stdio",
            "command": python,
            "args": [str(PERSONALKIN / "server.py")],
            "env": {
                "GARMIN_DB": str(garmin_sync / "garmin.duckdb"),
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
    print("─" * 44)

    TOTAL = 7

    step(1, TOTAL, "Locate garmin-sync")
    garmin_sync = confirm_garmin_sync()

    step(2, TOTAL, "Install dependencies")
    install_deps(garmin_sync)

    step(3, TOTAL, "Garmin authentication")
    garmin_auth(garmin_sync)

    step(4, TOTAL, "Initial sync")
    initial_sync(garmin_sync)

    step(5, TOTAL, "Physiology profile")
    fetch_physiology(garmin_sync)

    step(6, TOTAL, "macOS notifications")
    if sys.platform == "darwin":
        setup_notifications()
    else:
        info("Skipping — macOS only")

    step(7, TOTAL, "Terminal alias (ci)")
    setup_alias()

    print("\n" + "─" * 44)
    print("Setup complete.\n")
    show_mcp_config(garmin_sync)


if __name__ == "__main__":
    main()
