# English Translated EPG

Independent English-description XMLTV feed for TVP1, TVP2, TVP Polonia and Polsat 1.

Source: EPGShare01 Polish XMLTV feed. Titles and broadcast times are preserved. Programme descriptions are translated to English using the free `deep-translator` GoogleTranslator backend (unofficial, rate-limited).

## Setup
1. Enable GitHub Actions in this repository.
2. Run **Build English EPG** using **Actions → Run workflow**.
3. Once the workflow succeeds, add this EPG URL to TiviMate:

`https://raw.githubusercontent.com/Raffaello000/English-Translate-EPG/main/english-translated-epg.xml`

4. Manually assign the EPG channel to each TV channel in TiviMate.

Only selected channels are included. Translation may be incomplete if the free service rate-limits requests. Failed translations retain the original Polish text. Source attribution: https://epgshare01.online/

## Configuration
Edit `channels.json` to change channel names. The generator logs the actual channel IDs matched from the source. Translation cache is stored in `translation_cache.json`.

Note: This project is not affiliated with EPGShare01 or the broadcasters.
