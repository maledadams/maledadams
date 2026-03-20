from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


README_PATH = Path("README.md")
START_MARKERS = (
    "<!--START_SECTION:hackatime-->",
    "<!--START_SECTION:waka-->",
)
END_MARKERS = (
    "<!--END_SECTION:hackatime-->",
    "<!--END_SECTION:waka-->",
)
HACKATIME_API_ROOT = "https://hackatime.hackclub.com/api/v1"
ROLLING_DAYS = 30


def rolling_window() -> tuple[str, str]:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=ROLLING_DAYS - 1)
    return start_date.isoformat(), end_date.isoformat()


def load_payload() -> tuple[dict, str]:
    mock_file = os.getenv("WAKATIME_MOCK_FILE", "").strip()
    if mock_file:
        return json.loads(Path(mock_file).read_text(encoding="utf-8-sig")), "mock"

    api_key = os.getenv("WAKATIME_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing WAKATIME_API_KEY secret.")

    username = os.getenv("HACKATIME_USERNAME", "").strip()
    if not username:
        raise RuntimeError("Missing HACKATIME_USERNAME.")

    start_date, end_date = rolling_window()
    query = urlencode(
        {
            "api_key": api_key,
            "start_date": start_date,
            "end_date": end_date,
            "features": "languages,projects,editors",
        }
    )
    url = f"{HACKATIME_API_ROOT}/users/{username}/stats?{query}"
    request = Request(url, headers={"User-Agent": "maledadams-readme-updater"})

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body), url
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        raise RuntimeError(f"Unable to fetch coding stats.\n{url} -> HTTP {exc.code}: {body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to fetch coding stats.\n{url} -> {exc.reason}") from exc


def format_lines(items: Iterable[dict], empty_label: str) -> list[str]:
    def percent_value(item: dict) -> float:
        raw = str(item.get("percent", "0")).strip().rstrip("%")
        try:
            return float(raw)
        except ValueError:
            return 0.0

    rows = sorted(
        (item for item in items if item.get("name")),
        key=percent_value,
        reverse=True,
    )
    if not rows:
        return [f"- {empty_label}"]

    def format_percent(value: object) -> str:
        text = str(value).strip()
        if text.endswith("%"):
            return text
        return f"{text}%"

    return [f"- {item['name']}: {item.get('text', '0 secs')} ({format_percent(item.get('percent', '0'))})" for item in rows[:5]]


def render_section(payload: dict, source_url: str) -> str:
    data = payload.get("data") or {}
    status = data.get("status")
    if status == "pending_update":
        raise RuntimeError("Stats provider reports pending_update. Send a few editor heartbeats, then rerun the workflow.")

    if "languages" not in data:
        raise RuntimeError(f"Unexpected stats response from {source_url}: {json.dumps(payload)[:500]}")

    start_date, end_date = rolling_window()
    range_text = f"Last {ROLLING_DAYS} Days ({start_date} to {end_date})"
    total_time = data.get("human_readable_total") or data.get("text") or "0 secs"
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "",
        f"**{range_text}**",
        "",
        f"- Total coding time: {total_time}",
        f"- Source: Hackatime API",
        f"- Updated: {updated_at}",
        "",
        "**Languages**",
    ]
    lines.extend(format_lines(data.get("languages", []), "No language data yet"))
    lines.extend(
        [
            "",
            "**Projects**",
        ]
    )
    lines.extend(format_lines(data.get("projects", []), "No project data yet"))
    if data.get("editors"):
        lines.extend(
            [
                "",
                "**Editors**",
            ]
        )
        lines.extend(format_lines(data.get("editors", []), "No editor data yet"))
    lines.append("")
    return "\n".join(lines)


def update_readme(section: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    marker_pair = None
    for start_marker, end_marker in zip(START_MARKERS, END_MARKERS):
        if start_marker in readme and end_marker in readme:
            marker_pair = (start_marker, end_marker)
            break

    if marker_pair is None:
        raise RuntimeError("README.md is missing Hackatime section markers.")

    start_marker, end_marker = marker_pair

    start = readme.index(start_marker) + len(start_marker)
    end = readme.index(end_marker)
    updated = readme[:start] + "\n" + section + readme[end:]
    README_PATH.write_text(updated, encoding="utf-8")


def main() -> int:
    payload, source_url = load_payload()
    section = render_section(payload, source_url)
    update_readme(section)
    print(f"Updated README.md using {source_url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
