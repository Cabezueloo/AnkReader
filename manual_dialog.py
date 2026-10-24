# manual_dialog.py
# ================
# PyQt dialog for manually adding a word (without a Kindle).
# Reuses the full API enrichment pipeline including Pixabay image.
# Debug print() statements included throughout.

from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)
from aqt.operations import QueryOp
from aqt.utils import showWarning, tooltip

from .api_client import download_audio, download_image, lookup_word
from .kindle_sync import VocabEntry
from .note_creator import add_vocab_note, find_and_reset_existing_cards


class ManualWordDialog(QDialog):
    """A small dialog that lets the user type a word and create a card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AnkReader – Add word manually")
        self.setMinimumWidth(380)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Word input
        layout.addWidget(QLabel("English word:"))
        self._input = QLineEdit()
        self._input.setPlaceholderText("e.g. serendipity")
        layout.addWidget(self._input)

        # Deck name (optional)
        layout.addWidget(QLabel("Deck name (optional):"))
        self._deck_input = QLineEdit()
        self._deck_input.setPlaceholderText("Manual Vocabulary")
        layout.addWidget(self._deck_input)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        word = self._input.text().strip()
        if not word:
            showWarning("Please enter a word.", title="AnkReader")
            return

        deck = self._deck_input.text().strip() or "Manual Vocabulary"
        print(f"[AnkReader] ManualWordDialog: accepted word='{word}', deck='{deck}'")

        def _bg(col):
            print(f"[AnkReader] ManualWordDialog._bg: enriching '{word}'")
            result = lookup_word(word)

            audio = download_audio(word, result.audio_url)
            image = download_image(word)

            print(
                f"[AnkReader] ManualWordDialog._bg: done | "
                f"audio='{audio}' | image='{image}'"
            )
            return VocabEntry(
                word=word,
                book_title="",
                usage="",
                timestamp=0,
                meaning=result.meaning,
                definition=result.definition,
                part_of_speech=result.part_of_speech,
                phonetic_ipa=result.phonetic_ipa,
                audio_filename=audio,
                image_filename=image,
                synonyms=result.synonyms,
                example=result.example,
            )

        def _ok(entry: VocabEntry):
            print(f"[AnkReader] ManualWordDialog._ok: received entry for '{entry.word}'")
            if not entry.definition:
                showWarning(
                    f'Could not find a definition for "{entry.word}".\n\n'
                    'Check the terminal for details.',
                    title="AnkReader",
                )
                return

            existing_decks = find_and_reset_existing_cards(entry.word)
            if add_vocab_note(entry, deck_name=deck):
                mw.reset()
                if existing_decks:
                    tooltip(f'"{entry.word}" añadida a "{deck}". ¡Contador reiniciado en: {", ".join(existing_decks)}!', parent=mw)
                else:
                    tooltip(f'"{entry.word}" añadida al mazo "{deck}".', parent=mw)
                print(f"[AnkReader] ManualWordDialog._ok: note added OK")
            else:
                mw.reset()
                if existing_decks:
                    tooltip(f'"{entry.word}" ya existía en {", ".join(existing_decks)}. ¡Contador reiniciado para repasar!', parent=mw)
                else:
                    tooltip(f'"{entry.word}" ya existe (duplicado).', parent=mw)
                print(f"[AnkReader] ManualWordDialog._ok: duplicate, skipped")

            self.accept()

        op = QueryOp(parent=mw, op=_bg, success=_ok)
        op.with_progress(label=f'Looking up "{word}"…').run_in_background()
