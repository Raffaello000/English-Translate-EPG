#!/usr/bin/env python3
"""Build a small XMLTV file with English programme descriptions."""
import gzip
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from deep_translator import GoogleTranslator

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
    translator = GoogleTranslator(source="pl", target="en")
    result = ET.Element("tv", attrib=dict(root.attrib))
    for channel in selected_channels:
        result.append(channel)
    translated = failed = programmes = 0
    MAX_NEW_TRANSLATIONS = 40  # Small daily batch to respect free service limits
    stopped = False
    for programme in root.findall("programme"):
        if programme.get("channel") not in channel_ids:
            continue
        programmes += 1
        for desc in programme.findall("desc"):
            original = (desc.text or "").strip()
            if not original:
                continue
            if original not in cache and not stopped:
                if translated >= MAX_NEW_TRANSLATIONS:
                    stopped = True
                    print("Reached daily translation budget; remaining descriptions kept in Polish")
                    continue
                try:
                    # The free backend has a per-request length limit.
                    if len(original) > 4500:
                        raise ValueError("Description too long")
                    cache[original] = translator.translate(original)
                    translated += 1
                    time.sleep(1.5)
                except Exception as exc:
                    print("Translation unavailable; retaining Polish:", str(exc)[:120])
                    failed += 1
                    if "too many requests" in str(exc).lower() or "429" in str(exc):
                        stopped = True
                        print("Translation rate limit reached; stopping further requests")
                    continue
            if cache.get(original):
                desc.text = cache[original]
                desc.set("lang", "en")
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
