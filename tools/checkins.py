from datetime import date, timedelta
from pathlib import Path

CHECKINS_DIR = Path(__file__).parent.parent / "context" / "health" / "checkins"


def _load_checkin(date_str: str) -> dict:
    path = CHECKINS_DIR / f"{date_str}.md"
    if not path.exists():
        return {}
    parts = path.read_text().split("---")
    if len(parts) < 2:
        return {}
    fm = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            v = v.split("#")[0].strip()
            if v:
                fm[k.strip()] = v
    if len(parts) >= 3:
        notes = parts[2].strip()
        if notes:
            fm["notes"] = notes
    return fm


def get_checkins(days: int = 7) -> str:
    """
    Returns check-in data for the last N days (default 7).
    Includes mood (1-5), energy (1-5), training logged without watch, and freetext notes.
    Use to query subjective daily state or cross-reference with health metrics.
    """
    today   = date.today()
    entries = []

    for i in range(days - 1, -1, -1):
        d  = today - timedelta(days=i)
        ci = _load_checkin(d.isoformat())
        entries.append((d, ci))

    has_any = any(ci for _, ci in entries)
    if not has_any:
        return f"No check-ins found for the last {days} days."

    all_cis      = [ci for _, ci in entries if ci]
    has_training = any(ci.get("training") for ci in all_cis)

    lines = [f"# Check-ins — Last {days} days", ""]

    hdr = "| Date | Mood | Energy"
    sep = "|------|------|-------"
    if has_training: hdr += " | Training"; sep += "|---------"
    lines += [hdr + " |", sep + "|"]

    notes_by_date = {}
    for d, ci in entries:
        label = d.strftime("%a %b %d")
        if not ci:
            row = f"| {label} | — | —"
            if has_training: row += " | —"
            lines.append(row + " |")
            continue

        mood   = f"{ci['mood']}/5"   if ci.get("mood")   else "—"
        energy = f"{ci['energy']}/5" if ci.get("energy") else "—"
        row    = f"| {label} | {mood} | {energy}"
        if has_training: row += f" | {ci.get('training') or '—'}"
        lines.append(row + " |")

        if ci.get("notes"):
            notes_by_date[label] = ci["notes"]

    if notes_by_date:
        lines += ["", "**Notes:**", ""]
        for label, note in notes_by_date.items():
            lines.append(f"- **{label}:** {note}")

    mood_vals   = [float(ci["mood"])   for _, ci in entries if ci.get("mood")   and str(ci["mood"]).isdigit()]
    energy_vals = [float(ci["energy"]) for _, ci in entries if ci.get("energy") and str(ci["energy"]).isdigit()]
    filled      = sum(1 for _, ci in entries if ci)

    lines += ["", "---", ""]
    lines.append(f"**Coverage:** {filled}/{days} days")
    if mood_vals:   lines.append(f"**Avg mood:** {sum(mood_vals)/len(mood_vals):.1f}/5")
    if energy_vals: lines.append(f"**Avg energy:** {sum(energy_vals)/len(energy_vals):.1f}/5")

    return "\n".join(lines)
