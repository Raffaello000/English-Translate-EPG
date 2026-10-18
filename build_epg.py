#!/usr/bin/env python3
"""Build a small XMLTV file with English programme descriptions."""
import gzip
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from deep_translator import MyMemoryTranslator

SOURCE = os.getenv("EPG_SOURCE", "https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz")
OUTPUT = Path("english-translated-epg.xml")
CACHE_PATH = Path("translation_cache.json")
CONFIG_PATH = Path("channels.json")


def norm(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def download():
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "EnglishTranslatedEPG/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return ET.fromstring(data)


def xmltv_time(value):
    """Parse XMLTV timestamps, including timezone offsets."""
    if not value:
        return None
    match = re.match(r"^(\d{12})(?:\d{2})?\s*([+-]\d{4})?", value.strip())
    if not match:
        return None
    base = datetime.strptime(match.group(1), "%Y%m%d%H%M")
    offset = match.group(2)
    if offset:
        sign = 1 if offset[0] == "+" else -1
        minutes = sign * (int(offset[1:3]) * 60 + int(offset[3:5]))
        return base.replace(tzinfo=timezone(timedelta(minutes=minutes))).astimezone(timezone.utc)
    return base.replace(tzinfo=timezone.utc)


def main():
    root = download()
    names = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    aliases = {norm(alias): key for key, variants in names.items() for alias in variants}
    channel_ids = set()
    selected_channels = []
    for channel in root.findall("channel"):
        candidates = [channel.get("id", "")] + [(n.text or "") for n in channel.findall("display-name")]
        if any(norm(name) in aliases for name in candidates):
            channel_ids.add(channel.get("id"))
            selected_channels.append(channel)
    print("Matched channel IDs:", sorted(channel_ids))
    if len(channel_ids) < 4:
        raise RuntimeError("Expected four channels; verify source URL and channel IDs in channels.json")

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    translator = MyMemoryTranslator(source="pl-PL", target="en-GB")
    result = ET.Element("tv", attrib=dict(root.attrib))
    for channel in selected_channels:
        result.append(channel)
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=24)
    selected_programmes = []
    for p in root.findall("programme"):
        if p.get("channel") not in channel_ids:
            continue
        start = xmltv_time(p.get("start"))
        stop = xmltv_time(p.get("stop"))
        if start is None:
            continue
        # Include broadcasts that overlap the rolling 24-hour window.
        if start < horizon and (stop is None or stop > now):
            selected_programmes.append(p)
    print(f"Selected rolling EPG window: {now.isoformat()} to {horizon.isoformat()}")
    programmes = len(selected_programmes)
    translated = failed = 0
    MAX_NEW_TRANSLATIONS = 200  # Maximum new translations per run; service quotas still apply
    stopped = False

    # Translate all unique titles first, then descriptions, so guide titles
    # become useful before the limited free translation budget is exhausted.
    for tag in ("title", "desc"):
        for programme in selected_programmes:
            for element in programme.findall(tag):
                original = (element.text or "").strip()
                if not original or original in cache or stopped:
                    continue
                if translated >= MAX_NEW_TRANSLATIONS:
                    stopped = True
                    print("Reached translation budget; untranslated text kept in Polish")
                    break
                if len(original.encode("utf-8")) > 450:
                    continue
                try:
                    english = translator.translate(original)
                    if not english or english.strip() == original:
                        continue
                    cache[original] = english
                    translated += 1
                    time.sleep(2)
                except Exception as exc:
                    print("Translation unavailable:", str(exc)[:120])
                    failed += 1
                    if any(term in str(exc).lower() for term in ("too many", "429", "quota", "limit", "500")):
                        stopped = True
                        print("Rate limit reached; stopping further requests")
                        break

    for programme in selected_programmes:
        for tag in ("title", "desc"):
            for element in programme.findall(tag):
                original = (element.text or "").strip()
                if original in cache and cache[original]:
                    element.text = cache[original]
                    element.set("lang", "en")
        result.append(programme)
    if not programmes:
        raise RuntimeError("No programmes matched the selected channels")
    if translated == 0 and not cache:
        raise RuntimeError("No English translations obtained; free translator may be blocked. Refusing to publish Polish-only EPG.")
    ET.indent(result, space="  ")
    ET.ElementTree(result).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {programmes} programmes; new translations={translated}; failed={failed}; rate_limited_or_budget_reached={stopped}")


if __name__ == "__main__":
    main()
