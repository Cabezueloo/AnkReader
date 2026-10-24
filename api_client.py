# api_client.py
# =============
# HTTP helpers: Free Dictionary API (with Wiktionary & Datamuse fallbacks)
# + Google TTS audio + Pixabay images.
# All functions include debug print() statements for tracing.

from __future__ import annotations

import time
import os
import re
import urllib.request
import urllib.error
import json
from dataclasses import dataclass
import urllib.parse

from aqt import mw

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DictResult:
    """Parsed response from the dictionary APIs."""
    meaning: str = ""     # Spanish translation / significado
    definition: str = ""  # English definition
    part_of_speech: str = ""
    phonetic_ipa: str = ""
    audio_url: str = ""
    synonyms: str = ""    # comma-separated list
    example: str = ""     # example sentence from dictionary



# ---------------------------------------------------------------------------
# Configuration helper
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    """Retrieve addon configuration, falling back to config.json directly if needed."""
    cfg: dict = {}
    try:
        if mw and hasattr(mw, "addonManager"):
            addon_name = __name__.split(".")[0]
            cfg = mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        pass

    # Read from local config.json on disk if cfg is empty or missing pixabay_api_key
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as fh:
                disk_cfg = json.load(fh)
                if isinstance(disk_cfg, dict):
                    if not cfg:
                        cfg = disk_cfg
                    elif not cfg.get("pixabay_api_key") and disk_cfg.get("pixabay_api_key"):
                        cfg["pixabay_api_key"] = disk_cfg["pixabay_api_key"]
    except Exception as exc:
        print(f"[AnkReader] _get_config disk read error: {exc}")

    return cfg


# ---------------------------------------------------------------------------
# HTML text helper
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    """Strip HTML tags from strings."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# Fallback Dictionary: Wiktionary REST API + Datamuse
# ---------------------------------------------------------------------------

def _fallback_wiktionary_datamuse(word: str, result: DictResult) -> DictResult:
    """Enrich DictResult using Wiktionary + Datamuse when Free Dictionary API fails."""
    print(f"[AnkReader] _fallback_wiktionary_datamuse: querying Wiktionary for '{word}'")

    # 1. Wiktionary REST API
    try:
        url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{urllib.request.quote(word)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AnkReader/1.0 (contact@ankreader.org)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        en_sections = data.get("en", [])
        if en_sections:
            if not result.part_of_speech:
                result.part_of_speech = en_sections[0].get("partOfSpeech", "").lower()
            defs = en_sections[0].get("definitions", [])
            if defs:
                if not result.definition:
                    result.definition = _clean_html(defs[0].get("definition", ""))
                if not result.example:
                    examples = defs[0].get("examples", [])
                    if examples:
                        result.example = _clean_html(examples[0])
        print(
            f"[AnkReader] Wiktionary fallback OK: "
            f"pos='{result.part_of_speech}' | "
            f"def='{result.definition[:60]}' | "
            f"ex='{result.example[:60]}'"
        )
    except Exception as exc:
        print(f"[AnkReader] Wiktionary fallback error for '{word}': {exc}")

    # 2. Datamuse fallback if definition is still missing
    if not result.definition:
        try:
            print(f"[AnkReader] _fallback_wiktionary_datamuse: querying Datamuse definitions for '{word}'")
            url = f"https://api.datamuse.com/words?sp={urllib.request.quote(word)}&md=dp"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                dm_data = json.loads(resp.read().decode())
            if dm_data and isinstance(dm_data, list):
                first = dm_data[0]
                dm_defs = first.get("defs", [])
                if dm_defs:
                    raw_def = dm_defs[0]
                    if "\t" in raw_def:
                        pos_tag, def_text = raw_def.split("\t", 1)
                        if not result.part_of_speech:
                            pos_map = {"n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb"}
                            result.part_of_speech = pos_map.get(pos_tag, pos_tag)
                        result.definition = def_text.strip()
                    else:
                        result.definition = raw_def.strip()
            print(f"[AnkReader] Datamuse fallback OK: def='{result.definition[:60]}'")
        except Exception as exc:
            print(f"[AnkReader] Datamuse fallback error for '{word}': {exc}")

    # 3. Datamuse for synonyms if missing
    if not result.synonyms:
        try:
            url = f"https://api.datamuse.com/words?rel_syn={urllib.request.quote(word)}&max=5"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                syn_data = json.loads(resp.read().decode())
            syns = [
                item["word"]
                for item in syn_data
                if "word" in item and item["word"].lower() != word.lower()
            ]
            result.synonyms = ", ".join(syns[:5])
            print(f"[AnkReader] Datamuse synonyms: '{result.synonyms}'")
        except Exception as exc:
            print(f"[AnkReader] Datamuse synonyms error: {exc}")

    return result


# ---------------------------------------------------------------------------
# Meaning (Spanish translation) and IPA helpers
# ---------------------------------------------------------------------------

def _get_translation_meaning(word: str) -> str:
    """Intenta traducir con Google; si falla, usa DeepL como respaldo."""
    print(f"[AnkReader] _get_translation_meaning: intentando traducir '{word}' con Google")
    
    # 1. Intento con Google Translate
    try:
        url = (
            f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=es&dt=t&q="
            f"{urllib.request.quote(word)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
        if data and data[0] and data[0][0]:
            meaning = data[0][0][0].strip().capitalize()
            print(f"[AnkReader] Traducción (Google): '{word}' -> '{meaning}'")
            return meaning
    except Exception as exc:
        print(f"[AnkReader] Google falló para '{word}' ({exc}). Pasando a DeepL...")

    # 2. Respaldo automático con DeepL
    cfg = _get_config()
    deepl_key = cfg.get("deepl_api_key", "").strip()
    
    if not deepl_key:
        print("[AnkReader] ERROR: Google falló y no hay deepl_api_key configurada.")
        return "⚠️ Fallo de traducción"

    url_deepl = "https://api-free.deepl.com/v2/translate"
    data_deepl = urllib.parse.urlencode({"text": word, "target_lang": "ES"}).encode("utf-8")
    req_deepl = urllib.request.Request(
        url_deepl, 
        data=data_deepl, 
        headers={"Authorization": f"DeepL-Auth-Key {deepl_key}"}
    )
    
    try:
        with urllib.request.urlopen(req_deepl, timeout=5) as resp_deepl:
            result = json.loads(resp_deepl.read().decode())
            if "translations" in result:
                meaning = result["translations"][0]["text"].strip().capitalize()
                print(f"[AnkReader] Traducción (DeepL): '{word}' -> '{meaning}'")
                return meaning
    except Exception as exc:
        print(f"[AnkReader] Error en DeepL para '{word}': {exc}")
        
    return "⚠️ Revisar traducción"


def _get_wiktionary_ipa(word: str) -> str:
    """Fetch phonetic IPA from Wiktionary parse API."""
    print(f"[AnkReader] _get_wiktionary_ipa: querying Wiktionary wikitext IPA for '{word}'")
    try:
        url = (
            f"https://en.wiktionary.org/w/api.php?action=parse&page="
            f"{urllib.request.quote(word)}&prop=wikitext&format=json"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "AnkReader/1.0 (contact@ankreader.org)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        # Find {{IPA|en|/.../}}
        m = re.search(r"\{\{IPA\|en\|(/[^/]+/)(\]|\}|\|)", wikitext)
        if not m:
            m = re.search(r"\{\{IPA\|en\|([^|}]+)", wikitext)
        if m:
            ipa = m.group(1).strip()
            if not ipa.startswith("/"):
                ipa = f"/{ipa}/"
            print(f"[AnkReader] _get_wiktionary_ipa: found IPA='{ipa}'")
            return ipa
    except Exception as exc:
        print(f"[AnkReader] _get_wiktionary_ipa error for '{word}': {exc}")
    return ""


# ---------------------------------------------------------------------------
# Primary Free Dictionary API
# ---------------------------------------------------------------------------

_DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en"



def lookup_word(word: str) -> DictResult:
    """Query the Free Dictionary API for *word* with automatic Wiktionary fallback.

    Returns a DictResult enriched with definition, POS, IPA, audio URL,
    synonyms and an example sentence.
    """
    print(f"[AnkReader] lookup_word: querying dictionary for '{word}'")
    result = DictResult()
    result.meaning = _get_translation_meaning(word)
    url = f"{_DICT_API}/{urllib.request.quote(word)}"
    print(f"[AnkReader] lookup_word: URL -> {url}")

    data = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
        data = json.loads(raw)
        print(f"[AnkReader] lookup_word: HTTP 200 OK, length={len(raw)} chars")
    except urllib.error.HTTPError as exc:
        print(f"[AnkReader] lookup_word: HTTP error {exc.code} for '{word}'")
    except urllib.error.URLError as exc:
        print(f"[AnkReader] lookup_word: URL error '{exc.reason}' for '{word}'")
    except json.JSONDecodeError as exc:
        print(f"[AnkReader] lookup_word: JSON parse error for '{word}': {exc}")
    except OSError as exc:
        print(f"[AnkReader] lookup_word: OS error for '{word}': {exc}")

    if isinstance(data, list) and data:
        entry = data[0]

        # --- Phonetics: prefer an entry with text and audio ---
        for phon in entry.get("phonetics", []):
            if not result.phonetic_ipa and phon.get("text"):
                result.phonetic_ipa = phon["text"]
            if not result.audio_url and phon.get("audio"):
                result.audio_url = phon["audio"]
            if result.phonetic_ipa and result.audio_url:
                break

        if not result.phonetic_ipa:
            result.phonetic_ipa = entry.get("phonetic", "")

        print(
            f"[AnkReader] lookup_word: IPA='{result.phonetic_ipa}' | "
            f"audio_url='{result.audio_url}'"
        )

        # --- Meanings: definition, POS, synonyms, example sentence ---
        all_synonyms: list = []

        for meaning in entry.get("meanings", []):
            pos = meaning.get("partOfSpeech", "")
            defs = meaning.get("definitions", [])

            if not result.part_of_speech and pos:
                result.part_of_speech = pos

            if not result.definition and defs:
                result.definition = defs[0].get("definition", "")
                if not result.example:
                    result.example = defs[0].get("example", "")
                if not result.example:
                    for d in defs[1:]:
                        if d.get("example"):
                            result.example = d["example"]
                            break

            all_synonyms.extend(meaning.get("synonyms", []))
            for d in defs:
                all_synonyms.extend(d.get("synonyms", []))

        seen: set = set()
        unique_syns: list = []
        for s in all_synonyms:
            sl = s.lower()
            if sl not in seen and sl != word.lower():
                seen.add(sl)
                unique_syns.append(s)
            if len(unique_syns) >= 5:
                break
        result.synonyms = ", ".join(unique_syns)

    # --- Run fallback if primary API failed or returned no definition ---
    if not result.definition:
        print(f"[AnkReader] lookup_word: FreeDict gave no definition, running Wiktionary/Datamuse fallback...")
        result = _fallback_wiktionary_datamuse(word, result)

    # --- Run Wiktionary IPA fallback if phonetic_ipa is still empty ---
    if not result.phonetic_ipa:
        result.phonetic_ipa = _get_wiktionary_ipa(word)

    print(
        f"[AnkReader] lookup_word: finished for '{word}' -> "
        f"meaning='{result.meaning}' | "
        f"ipa='{result.phonetic_ipa}' | "
        f"pos='{result.part_of_speech}' | "
        f"def='{result.definition[:60]}' | "
        f"syn='{result.synonyms}' | "
        f"audio_url='{result.audio_url}'"
    )
    return result


# ---------------------------------------------------------------------------
# Media directory helper
# ---------------------------------------------------------------------------

def _media_dir() -> str:
    """Return the path to Anki's collection.media folder."""
    if mw and mw.col and mw.col.media:
        d = mw.col.media.dir()
        print(f"[AnkReader] _media_dir: {d}")
        return d
    print("[AnkReader] _media_dir: collection not open, returning ''")
    return ""


def _sanitise_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    return re.sub(r'[<>:"/\\|?*\s]', "_", name)


# ---------------------------------------------------------------------------
# Audio downloader (with Google TTS automatic fallback)
# ---------------------------------------------------------------------------

def download_audio(word: str, audio_url: str = "") -> str:
    """Download an .mp3 pronunciation file into collection.media.

    If audio_url is empty, falls back automatically to Google TTS
    so every note receives a high-quality audio pronunciation.
    Returns the bare filename on success, or '' on failure.
    """
    print(f"[AnkReader] download_audio: word='{word}' | url='{audio_url}'")

    if not audio_url:
        audio_url = (
            f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q="
            f"{urllib.request.quote(word)}"
        )
        print(f"[AnkReader] download_audio: no direct audio URL, using Google TTS -> {audio_url}")

    # Fix protocol-relative URLs (e.g. //ssl.gstatic.com/...)
    if audio_url.startswith("//"):
        audio_url = f"https:{audio_url}"
        print(f"[AnkReader] download_audio: fixed protocol-relative URL -> {audio_url}")

    media_dir = _media_dir()
    if not media_dir:
        print("[AnkReader] download_audio: media dir unavailable, skipping download")
        return ""

    filename = f"ankreader_pron_{_sanitise_filename(word)}.mp3"
    dest = os.path.join(media_dir, filename)
    print(f"[AnkReader] download_audio: destination -> {dest}")

    if os.path.isfile(dest):
        print(f"[AnkReader] download_audio: '{filename}' already cached, reusing")
        return filename

    try:
        req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        print(f"[AnkReader] download_audio: downloaded {len(data)} bytes")
        with open(dest, "wb") as fh:
            fh.write(data)
        print(f"[AnkReader] download_audio: saved '{filename}' OK")
        return filename
    except urllib.error.HTTPError as exc:
        print(f"[AnkReader] download_audio: HTTP {exc.code} for '{word}'")
    except urllib.error.URLError as exc:
        print(f"[AnkReader] download_audio: URL error '{exc.reason}' for '{word}'")
    except OSError as exc:
        print(f"[AnkReader] download_audio: OS error writing file: {exc}")

    # If initial audio_url failed and was not Google TTS, fallback to Google TTS
    if "translate_tts" not in audio_url:
        print(f"[AnkReader] download_audio: attempting Google TTS fallback for '{word}'")
        return download_audio(word, "")

    return ""


# ---------------------------------------------------------------------------
# Image downloader (Pixabay) – for BOTH Kindle and manual-entry modes
# ---------------------------------------------------------------------------

_PIXABAY_API = "https://pixabay.com/api/"


def download_image(word: str) -> str:
    """Fetch a representative image from Pixabay and save to collection.media.

    Returns the bare filename on success, or '' if no key configured
    or the request fails. Works for both Kindle sync and manual entry.
    """
    print(f"[AnkReader] download_image: fetching image for '{word}'")

    cfg = _get_config()
    api_key = cfg.get("pixabay_api_key", "").strip()
    if not api_key:
        print(
            "[AnkReader] download_image: pixabay_api_key not set in config.json – "
            "add your key at pixabay.com/api to enable images."
        )
        return ""

    params = urllib.request.quote(word)
    url = (
        f"{_PIXABAY_API}?key={api_key}&q={params}"
        f"&image_type=photo&per_page=3&safesearch=true"
    )
    print(f"[AnkReader] download_image: Pixabay URL -> {url[:80]}...")
    # AÑADE ESTA LÍNEA: Freno de 0.7 segundos para respetar las 100 peticiones/minuto
    time.sleep(0.7)
    hits = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        hits = data.get("hits", [])
        print(f"[AnkReader] download_image: Pixabay returned {len(hits)} hits")
    except urllib.error.HTTPError as exc:
        print(f"[AnkReader] download_image: Pixabay HTTP {exc.code}")
        return ""
    except urllib.error.URLError as exc:
        print(f"[AnkReader] download_image: Pixabay URL error '{exc.reason}'")
        return ""
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[AnkReader] download_image: error reading Pixabay response: {exc}")
        return ""

    if not hits:
        print(f"[AnkReader] download_image: no images found for '{word}'")
        return ""

    img_url = hits[0].get("webformatURL", "")
    if not img_url:
        print(f"[AnkReader] download_image: no webformatURL in first hit for '{word}'")
        return ""

    print(f"[AnkReader] download_image: image URL -> {img_url}")

    ext = os.path.splitext(img_url.split("?")[0])[1] or ".jpg"
    filename = f"ankreader_img_{_sanitise_filename(word)}{ext}"
    media_dir = _media_dir()
    if not media_dir:
        print("[AnkReader] download_image: media dir unavailable, skipping")
        return ""
    dest = os.path.join(media_dir, filename)

    if os.path.isfile(dest):
        print(f"[AnkReader] download_image: '{filename}' already cached, reusing")
        return filename

    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_data = resp.read()
        print(f"[AnkReader] download_image: downloaded {len(img_data)} bytes")
        with open(dest, "wb") as fh:
            fh.write(img_data)
        print(f"[AnkReader] download_image: saved '{filename}' OK")
    except urllib.error.HTTPError as exc:
        print(f"[AnkReader] download_image: HTTP {exc.code} downloading image")
        return ""
    except urllib.error.URLError as exc:
        print(f"[AnkReader] download_image: URL error '{exc.reason}' downloading image")
        return ""
    except OSError as exc:
        print(f"[AnkReader] download_image: OS error writing image: {exc}")
        return ""

    return filename
