# note_creator.py
# ===============
# Interfaces with Anki's internal Python API to create decks, manage note
# types (models), and add notes programmatically.
# Debug print() statements are included at every key step.

import re
from typing import List, Optional, Set

from anki.consts import MODEL_STD
from anki.models import NotetypeDict
from aqt import mw

from .kindle_sync import VocabEntry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_NAME = "AnkReader Vocabulary"

FRONT_TEMPLATE = """\
<div class="ankreader-front">
  <div class="word">{{Word}}</div>
  {{#Phonetic}}
  <div class="phonetic">[{{Phonetic}}]</div>
  {{/Phonetic}}
  {{#Audio}}
  <div class="audio">{{Audio}}</div>
  {{/Audio}}
</div>
"""

BACK_TEMPLATE = """\
{{FrontSide}}
<hr id="answer">
<div class="ankreader-back">
  {{#Meaning}}
  <div class="meaning">{{Meaning}}</div>
  {{/Meaning}}
  {{#PartOfSpeech}}
  <div><span class="pos">{{PartOfSpeech}}</span></div>
  {{/PartOfSpeech}}
  {{#Definition}}
  <div class="definition">{{Definition}}</div>
  {{/Definition}}
  {{#Synonyms}}
  <div><span class="synonyms"><strong>Synonyms:</strong> {{Synonyms}}</span></div>
  {{/Synonyms}}
  {{#Example}}
  <div class="example">&ldquo;{{Example}}&rdquo;</div>
  {{/Example}}
  {{#Context}}
  <blockquote class="context">
    <strong>From the book:</strong> {{Context}}
  </blockquote>
  {{/Context}}
  {{#Image}}
  <div class="image">{{Image}}</div>
  {{/Image}}
</div>
"""

MODEL_CSS = """\
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 18px;
  text-align: center;
  color: #1e293b;
  background-color: #ffffff;
  padding: 1.8em 1.2em;
  line-height: 1.5;
}

/* Dark mode support */
.nightMode .card, .night_mode .card {
  background-color: #1a1b23;
  color: #f1f5f9;
}

/* Front card */
.ankreader-front .word {
  font-size: 2.3em;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #0f172a;
  margin-bottom: 0.15em;
}
.nightMode .ankreader-front .word, .night_mode .ankreader-front .word {
  color: #f8fafc;
}

.ankreader-front .phonetic {
  font-size: 1.15em;
  color: #64748b;
  margin: 0.2em 0 0.5em 0;
  font-family: "Segoe UI", "Lucida Sans Unicode", sans-serif;
}
.nightMode .ankreader-front .phonetic, .night_mode .ankreader-front .phonetic {
  color: #94a3b8;
}

.ankreader-front .audio {
  margin-top: 0.4em;
}

/* Back card */
hr#answer {
  border: none;
  height: 1px;
  background: #e2e8f0;
  margin: 1.2em auto;
  max-width: 80%;
}
.nightMode hr#answer, .night_mode hr#answer {
  background: #334155;
}

.ankreader-back .meaning {
  font-size: 1.65em;
  font-weight: 700;
  color: #0284c7;
  margin: 0.2em 0 0.2em 0;
}
.nightMode .ankreader-back .meaning, .night_mode .ankreader-back .meaning {
  color: #38bdf8;
}

.ankreader-back .pos {
  display: inline-block;
  font-size: 0.85em;
  font-weight: 600;
  color: #6366f1;
  background: #eef2ff;
  padding: 2px 10px;
  border-radius: 12px;
  margin: 0.2em 0 0.6em 0;
  text-transform: lowercase;
}
.nightMode .ankreader-back .pos, .night_mode .ankreader-back .pos {
  color: #c7d2fe;
  background: #312e81;
}

.ankreader-back .definition {
  font-size: 1.1em;
  color: #334155;
  margin: 0.5em auto;
  max-width: 540px;
  line-height: 1.5;
}
.nightMode .ankreader-back .definition, .night_mode .ankreader-back .definition {
  color: #e2e8f0;
}

.ankreader-back .synonyms {
  display: inline-block;
  font-size: 0.88em;
  color: #047857;
  background: #ecfdf5;
  padding: 4px 12px;
  border-radius: 8px;
  margin: 0.4em 0;
  max-width: 520px;
}
.nightMode .ankreader-back .synonyms, .night_mode .ankreader-back .synonyms {
  color: #34d399;
  background: #064e3b;
}

.ankreader-back .example {
  font-size: 0.95em;
  color: #475569;
  font-style: italic;
  margin: 0.6em auto;
  max-width: 520px;
}
.nightMode .ankreader-back .example, .night_mode .ankreader-back .example {
  color: #94a3b8;
}

.ankreader-back .context {
  border-left: 3px solid #38bdf8;
  background: #f8fafc;
  padding: 0.8em 1.1em;
  border-radius: 0 8px 8px 0;
  color: #334155;
  font-style: italic;
  text-align: left;
  margin: 1em auto;
  max-width: 520px;
}
.nightMode .ankreader-back .context, .night_mode .ankreader-back .context {
  background: #232530;
  color: #cbd5e1;
  border-left-color: #0284c7;
}

.ankreader-back .image {
  margin-top: 1em;
}
.ankreader-back .image img {
  max-width: 320px;
  max-height: 240px;
  object-fit: cover;
  border-radius: 10px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
}
"""

# All fields in order
FIELD_NAMES = [
    "Word",
    "Phonetic",
    "Audio",
    "Meaning",
    "PartOfSpeech",
    "Definition",
    "Synonyms",
    "Example",
    "Context",
    "Image",
]


# ---------------------------------------------------------------------------
# Model (note type) management
# ---------------------------------------------------------------------------

def _get_or_create_model() -> NotetypeDict:
    """Return the 'AnkReader Vocabulary' note type, creating or updating it if needed."""
    col = mw.col
    model = col.models.by_name(MODEL_NAME)
    if model is not None:
        print(f"[AnkReader] _get_or_create_model: checking existing model '{MODEL_NAME}'")
        existing_fields = set(col.models.field_names(model))
        modified = False
        for name in FIELD_NAMES:
            if name not in existing_fields:
                print(f"[AnkReader] _get_or_create_model: adding missing field '{name}' to existing model")
                field = col.models.new_field(name)
                col.models.add_field(model, field)
                existing_fields.add(name)
                modified = True

        # Always check and update templates and CSS if they changed
        if model.get("tmpls"):
            if model["tmpls"][0].get("qfmt") != FRONT_TEMPLATE or model["tmpls"][0].get("afmt") != BACK_TEMPLATE:
                model["tmpls"][0]["qfmt"] = FRONT_TEMPLATE
                model["tmpls"][0]["afmt"] = BACK_TEMPLATE
                modified = True
        if model.get("css") != MODEL_CSS:
            model["css"] = MODEL_CSS
            modified = True

        if modified:
            col.models.save(model)
            print(f"[AnkReader] _get_or_create_model: model '{MODEL_NAME}' updated with all fields OK")

        return model

    print(f"[AnkReader] _get_or_create_model: creating new model '{MODEL_NAME}'")

    model = col.models.new(MODEL_NAME)
    model["type"] = MODEL_STD

    for name in FIELD_NAMES:
        field = col.models.new_field(name)
        col.models.add_field(model, field)
        print(f"[AnkReader] _get_or_create_model: added field '{name}'")

    tmpl = col.models.new_template("Card 1")
    tmpl["qfmt"] = FRONT_TEMPLATE
    tmpl["afmt"] = BACK_TEMPLATE
    col.models.add_template(model, tmpl)

    model["css"] = MODEL_CSS
    col.models.add(model)
    print(f"[AnkReader] _get_or_create_model: model created OK with {len(FIELD_NAMES)} fields")
    return model


# ---------------------------------------------------------------------------
# Deck management
# ---------------------------------------------------------------------------

def _get_or_create_deck(deck_name: str) -> int:
    """Return the deck ID for *deck_name*, creating it if necessary.

    Supports '::' separators for sub-decks (e.g. 'Kindle::Harry Potter').
    """
    col = mw.col
    print(f"[AnkReader] _get_or_create_deck: looking for deck '{deck_name}'")
    deck_id = col.decks.id_for_name(deck_name)
    if deck_id is not None:
        print(f"[AnkReader] _get_or_create_deck: found existing deck id={deck_id}")
        return deck_id
    # id() creates the deck (and parent decks) on the fly
    deck_id = col.decks.id(deck_name)
    print(f"[AnkReader] _get_or_create_deck: created new deck id={deck_id}")
    return deck_id


# ---------------------------------------------------------------------------
# Note creation
# ---------------------------------------------------------------------------

def build_deck_name(book_title: str) -> str:
    """Derive a deck name from the book title.

    Uses the 'target_deck_prefix' from config (defaults to 'Kindle::').
    """
    cfg = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    prefix = cfg.get("target_deck_prefix", "Kindle::")
    title = book_title.strip().removesuffix(".mobi").removesuffix(".azw3")
    deck_name = f"{prefix}{title}"
    print(f"[AnkReader] build_deck_name: '{book_title}' -> '{deck_name}'")
    return deck_name


# ---------------------------------------------------------------------------
# Existing card detection & schedule reset
# ---------------------------------------------------------------------------

def find_and_reset_existing_cards(word: str) -> List[str]:
    """Search for any existing cards in Anki whose main word matches *word*.

    Resets their review schedule/counters back to new (since the user forgot them),
    and returns a sorted list of deck names where matching cards were found.
    """
    col = mw.col
    if not col:
        return []

    clean_target = re.sub(r"<[^>]+>", "", word).strip().lower()
    if not clean_target:
        return []

    found_decks: Set[str] = set()
    cards_to_reset: List[int] = []

    try:
        nids = col.find_notes(f'"{clean_target}"')
        for nid in nids:
            try:
                note = col.get_note(nid)
                if not note.fields:
                    continue
                first_field_clean = re.sub(r"<[^>]+>", "", note.fields[0]).strip().lower()
                if first_field_clean == clean_target:
                    for card in note.cards():
                        deck_dict = col.decks.get(card.did)
                        dname = deck_dict.get("name", "Mazo sin nombre") if deck_dict else "Mazo sin nombre"
                        found_decks.add(dname)
                        cards_to_reset.append(card.id)
            except Exception as e:
                print(f"[AnkReader] Error inspecting note {nid}: {e}")

        if cards_to_reset:
            print(
                f"[AnkReader] Resetting schedule for '{clean_target}' on {len(cards_to_reset)} card(s) "
                f"in decks: {list(found_decks)}"
            )
            try:
                if hasattr(col.sched, "schedule_cards_as_new"):
                    col.sched.schedule_cards_as_new(cards_to_reset, restore_position=False, reset_counts=True)
                elif hasattr(col.sched, "reset_cards"):
                    col.sched.reset_cards(cards_to_reset)
            except Exception as exc:
                print(f"[AnkReader] Error resetting schedule for '{word}': {exc}")

    except Exception as exc:
        print(f"[AnkReader] find_and_reset_existing_cards error for '{word}': {exc}")

    return sorted(list(found_decks))


def add_vocab_note(
    entry: VocabEntry,
    deck_name: Optional[str] = None,
) -> int:
    """Create and add a note for the given VocabEntry.

    Returns True if the note was added, False if it was a duplicate/empty.
    """
    print(f"[AnkReader] add_vocab_note: processing word='{entry.word}'")
    col = mw.col

    if deck_name is None:
        deck_name = build_deck_name(entry.book_title)

    deck_id = _get_or_create_deck(deck_name)
    model = _get_or_create_model()

    # Point the model at the right deck so new notes land there
    model["did"] = deck_id
    col.models.update_dict(model)

    note = col.new_note(model)

    # --- Populate fields safely --------------------------------------------
    def _set_field(field_name: str, val: str):
        if field_name in note:
            note[field_name] = val
        else:
            print(f"[AnkReader] add_vocab_note: warning, field '{field_name}' not in note type")

    _set_field("Word", entry.word)
    _set_field("Phonetic", entry.phonetic_ipa)
    _set_field("Meaning", entry.meaning)
    _set_field("PartOfSpeech", entry.part_of_speech)
    _set_field("Definition", entry.definition)
    _set_field("Synonyms", entry.synonyms)
    _set_field("Example", entry.example)
    _set_field("Context", entry.usage)

    if entry.audio_filename:
        _set_field("Audio", f"[sound:{entry.audio_filename}]")
        print(f"[AnkReader] add_vocab_note: audio -> [sound:{entry.audio_filename}]")
    else:
        _set_field("Audio", "")
        print("[AnkReader] add_vocab_note: no audio")

    if entry.image_filename:
        _set_field("Image", f'<img src="{entry.image_filename}">')
        print(f"[AnkReader] add_vocab_note: image -> {entry.image_filename}")
    else:
        _set_field("Image", "")
        print("[AnkReader] add_vocab_note: no image")

    # --- Duplicate check (by first field = Word) ---------------------------
    dupe_status = note.duplicate_or_empty()
    if dupe_status:
        print(f"[AnkReader] add_vocab_note: omitiendo '{entry.word}' (duplicado o vacío)")
        return 0 # Devolvemos 0 en lugar de False

    col.add_note(note, deck_id)
    print(f"[AnkReader] add_vocab_note: nota añadida. ID={note.id}")
    return note.id # Devolvemos el ID exacto de la carta en lugar de True
