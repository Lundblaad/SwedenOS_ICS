#!/usr/bin/env python3
"""
Generate an iCalendar (.ics) file containing ONLY Sweden (SWE) men's Olympic ice hockey games,
published via GitHub Pages from the /docs folder.

Source schedule page:
  https://www.iihf.com/en/events/2026/olympic-m/schedule

Key change vs manual ICS writing:
- Uses the `icalendar` library to produce Apple Calendar–compatible ICS (proper RFC5545 formatting/line folding).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytz
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

IIHF_URL = "https://www.iihf.com/en/events/2026/olympic-m/schedule"
YEAR = 2026

# The IIHF schedule page times are local to the event host.
# Using Europe/Rome is appropriate for Milano-Cortina 2026.
TZ_LOCAL = pytz.timezone("Europe/Rome")
TZ_UTC = pytz.UTC

DEFAULT_GAME_DURATION = timedelta(hours=2, minutes=30)

# The schedule page commonly contains date lines like "13 Feb"
DATE_RE = re.compile(r"^(?P<day>\d{1,2})\s+Feb$")
# Time like "12:10"
TIME_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})$")
# Matchup like "FIN vs SWE"
MATCH_RE = re.compile(r"^(?P<a>[A-Z]{3})\s+vs\s+(?P<b>[A-Z]{3})$")


@dataclass(frozen=True)
class Game:
    uid: str
    dtstart_utc: datetime
    dtend_utc: datetime
    summary: str
    location: str | None = None


def fetch_lines() -> list[str]:
    """Fetch the schedule page and return normalized non-empty text lines."""
    r = requests.get(IIHF_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def parse_games(lines: list[str]) -> list[Game]:
    """
    Parse schedule text lines into Sweden games.
    This is heuristic: it looks for:
      - a date marker (e.g. '13 Feb')
      - a match line (e.g. 'FIN vs SWE')
      - a nearby time line (e.g. '12:10')
      - a nearby venue-ish line (best effort)
    """
    games: list[Game] = []
    current_date_local: datetime | None = None

    i = 0
    while i < len(lines):
        mdate = DATE_RE.match(lines[i])
        if mdate:
            day = int(mdate.group("day"))
            # Midnight local on that date; we'll set hour/min later
            current_date_local = TZ_LOCAL.localize(datetime(YEAR, 2, day, 0, 0, 0))
            i += 1
            continue

        mmatch = MATCH_RE.match(lines[i])
        if mmatch and current_date_local:
            a = mmatch.group("a")
            b = mmatch.group("b")

            # Only Sweden games
            if a != "SWE" and b != "SWE":
                i += 1
                continue

            # Find a time line within the next few lines
            tline = None
            for j in range(1, 10):
                if i + j < len(lines) and TIME_RE.match(lines[i + j]):
                    tline = lines[i + j]
                    break
            if not tline:
                i += 1
                continue

            mt = TIME_RE.match(tline)
            hh = int(mt.group("h"))
            mm = int(mt.group("m"))

            start_local = current_date_local.replace(hour=hh, minute=mm, second=0)
            end_local = start_local + DEFAULT_GAME_DURATION

            start_utc = start_local.astimezone(TZ_UTC)
            end_utc = end_local.astimezone(TZ_UTC)

            # Best-effort venue detection (optional)
            venue = None
            for j in range(1, 6):
                if i + j < len(lines):
                    cand = lines[i + j]
                    # These heuristics are intentionally conservative
                    if any(x in cand for x in ("Milano", "Cortina", "Arena", "Ice", "Forum")):
                        venue = cand
                        break

            opponent = b if a == "SWE" else a
            summary = f"Sweden vs {opponent} (Men's Ice Hockey)"

            # Stable UID:
            # If IIHF provides a real match id in the page text, prefer it.
            # Fallback: date + teams + time is stable enough for subscription updates.
            uid = f"{start_local.strftime('%Y%m%dT%H%M')}-{a}vs{b}@lundblaad.github.io"

            games.append(
                Game(
                    uid=uid,
                    dtstart_utc=start_utc,
                    dtend_utc=end_utc,
                    summary=summary,
                    location=venue,
                )
            )

        i += 1

    # Deduplicate by UID
    uniq: dict[str, Game] = {g.uid: g for g in games}
    return sorted(uniq.values(), key=lambda g: g.dtstart_utc)


def build_ics(games: list[Game]) -> str:
    """
    Build an Apple Calendar–friendly ICS using `icalendar` (handles line folding and encoding).
    """
    cal = Calendar()
    cal.add("prodid", "-//SWE Men Hockey//GitHub Pages//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    # Helpful Apple-specific properties (safe for other clients)
    cal.add("X-WR-CALNAME", "Sweden – Men's Ice Hockey (OS)")
    cal.add("X-WR-TIMEZONE", "UTC")

    now = datetime.now(TZ_UTC)

    for g in games:
        ev = Event()
        ev.add("uid", g.uid)
        ev.add("dtstamp", now)
        ev.add("dtstart", g.dtstart_utc)
        ev.add("dtend", g.dtend_utc)
        ev.add("summary", g.summary)
        if g.location:
            ev.add("location", g.location)

        # Optional: mark as confirmed
        ev.add("status", "CONFIRMED")

        cal.add_component(ev)

    return cal.to_ical().decode("utf-8")


def main() -> None:
    lines = fetch_lines()
    games = parse_games(lines)
    ics_text = build_ics(games)

    # Write to docs/ so GitHub Pages can serve it
    import pathlib

    outpath = pathlib.Path("docs") / "swe-men-hockey.ics"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(ics_text, encoding="utf-8")


if __name__ == "__main__":
    main()
