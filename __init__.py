# AnkReader – Kindle Vocabulary Importer
# ========================================
# Entry point loaded by Anki.  Registers menu actions and hooks.

from aqt import mw, gui_hooks
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo, tooltip

from .sync_manager import run_kindle_sync
from .manual_dialog import ManualWordDialog

from . import mobile_server
# ---------------------------------------------------------------------------
# Menu setup
# ---------------------------------------------------------------------------

def _on_kindle_sync() -> None:
    """Trigger a full Kindle → Anki sync from the menu."""
    run_kindle_sync()


def _on_manual_add() -> None:
    """Open the manual-entry dialog."""
    dialog = ManualWordDialog(mw)
    dialog.exec()


def _setup_menu() -> None:
    """Create the AnkReader sub-menu under *Tools*."""
    menu = QMenu("AnkReader", mw)

    act_sync = QAction("Sync Kindle vocabulary", mw)
    act_sync.triggered.connect(_on_kindle_sync)
    menu.addAction(act_sync)

    act_manual = QAction("Add word manually…", mw)
    act_manual.triggered.connect(_on_manual_add)
    menu.addAction(act_manual)

    mw.form.menuTools.addMenu(menu)


gui_hooks.main_window_did_init.append(_setup_menu)
