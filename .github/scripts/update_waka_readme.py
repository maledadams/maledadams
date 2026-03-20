from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


README_PATH = Path("README.md")
START_MARKER = "<!--START_SECTION:waka-->"
END_MARKER = "<!--END_SECTION:waka-->"
DEFAULT_API_URLS = (
    "https://wakatime.com/api/v1/",
    "https://hackatime.hackclub.com/api/hackatime/v1/",
)


def candidate_api_urls() -> list[str]:
    urls: list[str] = []
    configured = os.getenv("WAKATIME_API_URL", "").strip()
    if configured:
        urls.append(configured)
    urls.extend(DEFAULT_API_URLS)

    deduped: list[str] = []
    for url in urls:
        normalized = url.rstrip("/") + "/"
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def load_payload() -> tuple[dict, str]:
    mock_file = os.getenv("WAKATIME_MOCK_FILE", "").strip()
    if mock_file:
        return json.loads(Path(mock_file).read_text(encoding="utf-8-sig")), "mock"

    api_key = os.getenv("WAKATIME_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing WAKATIME_API_KEY secret.")

    errors: list[str] = []
    for base_url in candidate_api_urls():
        url = f"{base_url}users/current/stats/last_7_days?{urlencode({'api_key': api_key})}"
        request = Request(url, headers={"User-Agent": "maledadams-readme-updater"})
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body), base_url
        except HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            errors.append(f"{base_url} -> HTTP {exc.code}: {body[:200]}")
        except URLError as exc:
            errors.append(f"{base_url} -> {exc.reason}")

    joined = "\n".join(errors) if errors else "No endpoints attempted."
    raise RuntimeError(f"Unable to fetch coding stats.\n{joined}")


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

    range_text = data.get("range") or "Last 7 Days"
    total_time = data.get("human_readable_total") or data.get("text") or "0 secs"
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "",
        f"**{range_text}**",
        "",
        f"- Total coding time: {total_time}",
        f"- Source: {source_url}",
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
    if START_MARKER not in readme or END_MARKER not in readme:
        raise RuntimeError("README.md is missing waka section markers.")

    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
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
