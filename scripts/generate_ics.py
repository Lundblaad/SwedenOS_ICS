#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

IIHF_URL = "https://www.iihf.com/en/events/2026/olympic-m/schedule"
YEAR = 2026

# Schedule page shows local time at venues in Italy; treat as Europe/Rome.
TZ_LOCAL = ZoneInfo("Europe/Rome")
TZ_UTC = ZoneInfo("UTC")

# If you prefer Sweden local time in the calendar, set TZ_LOCAL = ZoneInfo("Europe/Stockholm")
# and keep DTSTART/DTEND as floating/local (but UTC is usually safest for subscribers).

DEFAULT_GAME_DURATION = timedelta(hours=2, minutes=30)

DATE_RE = re.compile(r"^(?P<day>\d{1,2})\s+Feb$")
TIME_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})$")
MATCH_RE = re.compile(r"^(?P<a>[A-Z]{3})\s+vs\s+(?P<b>[A-Z]{3})$")

@dataclass
class Game:
    uid: str
    dtstart_utc: datetime
    dtend_utc: datetime
    summary: str
    location: str | None = None

def escape_ics(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace("\n", "\\n")
         .replace(",", "\\,")
         .replace(";", "\\;")
    )

def fmt_utc(dt: datetime) -> str:
    dt = dt.astimezone(TZ_UTC)
    return dt.strftime("%Y%m%dT%H%M%SZ")

def fetch_lines() -> list[str]:
    r = requests.get(IIHF_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n")
    # Normalize lines
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]  # drop empties
    return lines

def parse_games(lines: list[str]) -> list[Game]:
    games: list[Game] = []
    current_date: datetime | None = None

    # We look for date markers like "13 Feb", then a match line like "FIN vs SWE",
    # then the next venue-ish line, then the next time line like "12:10".
    i = 0
    while i < len(lines):
        mdate = DATE_RE.match(lines[i])
        if mdate:
            day = int(mdate.group("day"))
            current_date = datetime(YEAR, 2, day, 0, 0, tzinfo=TZ_LOCAL)
            i += 1
            continue

        mmatch = MATCH_RE.match(lines[i])
        if mmatch and current_date:
            a = mmatch.group("a")
            b = mmatch.group("b")

            # Only Sweden games
            if a != "SWE" and b != "SWE":
                i += 1
                continue

            # Try to find venue (next 1–3 lines that look like a location)
            venue = None
            for j in range(1, 4):
                if i + j < len(lines) and ("Milano" in lines[i + j] or "Group" in lines[i + j]):
                    venue = lines[i + j]
                    break

            # Find time (next 1–8 lines)
            tline = None
            for j in range(1, 9):
                if i + j < len(lines) and TIME_RE.match(lines[i + j]):
                    tline = lines[i + j]
                    break
            if not tline:
                i += 1
                continue

            mt = TIME_RE.match(tline)
            hh, mm = int(mt.group("h")), int(mt.group("m"))

            start_local = current_date.replace(hour=hh, minute=mm)
            end_local = start_local + DEFAULT_GAME_DURATION

            start_utc = start_local.astimezone(TZ_UTC)
            end_utc = end_local.astimezone(TZ_UTC)

            opponent = b if a == "SWE" else a
            summary = f"Sweden vs {opponent} (Men's Ice Hockey)"
            # UID needs to be stable; use date+teams+time as a fallback
            uid = f"{YEAR}022{start_local.day:02d}-{a}vs{b}-{hh:02d}{mm:02d}@swe-men-hockey"

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

    # Deduplicate by UID (in case page repeats items in text)
    uniq: dict[str, Game] = {}
    for g in games:
        uniq[g.uid] = g
    return sorted(uniq.values(), key=lambda g: g.dtstart_utc)

def build_ics(games: list[Game]) -> str:
    now = datetime.now(tz=TZ_UTC)
    out: list[str] = []
    out.append("BEGIN:VCALENDAR")
    out.append("VERSION:2.0")
    out.append("PRODID:-//SWE Men Hockey//GitHub Pages//EN")
    out.append("CALSCALE:GREGORIAN")
    out.append("METHOD:PUBLISH")

    for g in games:
        out.append("BEGIN:VEVENT")
        out.append(f"UID:{escape_ics(g.uid)}")
        out.append(f"DTSTAMP:{fmt_utc(now)}")
        out.append(f"DTSTART:{fmt_utc(g.dtstart_utc)}")
        out.append(f"DTEND:{fmt_utc(g.dtend_utc)}")
        out.append(f"SUMMARY:{escape_ics(g.summary)}")
        if g.location:
            out.append(f"LOCATION:{escape_ics(g.location)}")
        out.append("END:VEVENT")

    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"

def main() -> None:
    lines = fetch_lines()
    games = parse_games(lines)
    ics = build_ics(games)

    # Write into docs/ for GitHub Pages publishing
    import pathlib
    outpath = pathlib.Path("docs") / "swe-men-hockey.ics"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(ics, encoding="utf-8")

if __name__ == "__main__":
    main()
