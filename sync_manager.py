# sync_manager.py
from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from aqt import mw
from aqt.operations import QueryOp
from aqt.utils import showInfo, showWarning, tooltip

from .api_client import download_audio, download_image, lookup_word
from .kindle_sync import (
    VocabEntry,
    fetch_new_entries,
    find_vocab_db,
    update_last_sync,
    _get_config,
)
from .note_creator import add_vocab_note, find_and_reset_existing_cards


# ===========================================================================
# COLA DE IMÁGENES EN SEGUNDO PLANO
# ===========================================================================

# Cola segura para pasar tareas al hilo de imágenes
IMAGE_QUEUE = queue.Queue()

def _image_worker():
    """Hilo daemon: descarga imágenes y actualiza la carta de Anki asíncronamente."""
    while True:
        item = IMAGE_QUEUE.get()
        if item is None:
            break
            
        note_id, word = item
        print(f"[AnkReader/Worker] Buscando imagen para '{word}'...")
        
        # Esto usará la función que ya tiene tu time.sleep(0.7) para respetar a Pixabay
        img_filename = download_image(word)
        
        if img_filename:
            # Actualizar la base de datos de Anki DEBE hacerse en el hilo principal
            def _update_note_ui(nid=note_id, img=img_filename, w=word):
                try:
                    if mw.col:
                        note = mw.col.get_note(nid)
                        note["Image"] = f'<img src="{img}">'
                        mw.col.update_note(note)
                        print(f"[AnkReader/Worker] Imagen pegada en la carta de '{w}'")
                except Exception as e:
                    print(f"[AnkReader/Worker] Error actualizando carta {nid}: {e}")

            mw.taskman.run_on_main(_update_note_ui)
            
        IMAGE_QUEUE.task_done()

# Iniciamos el trabajador invisible al cargar el módulo
_worker_thread = threading.Thread(target=_image_worker, daemon=True)
_worker_thread.start()


# ===========================================================================
# FLUJO PRINCIPAL DE SINCRONIZACIÓN (Súper rápido)
# ===========================================================================

def _enrich_entry(entry: VocabEntry) -> VocabEntry:
    """Descarga texto y audio. NO descarga imagen para no bloquear."""
    print(f"[AnkReader] _enrich_entry: START '{entry.word}'")
    result = lookup_word(entry.word)
    entry.meaning = result.meaning
    entry.definition = result.definition
    entry.part_of_speech = result.part_of_speech
    entry.phonetic_ipa = result.phonetic_ipa
    entry.synonyms = result.synonyms
    entry.example = result.example
    entry.audio_filename = download_audio(entry.word, result.audio_url)
    
    # Dejamos la imagen vacía; el trabajador de fondo se encargará luego
    entry.image_filename = ""
    return entry


def _enrich_all(entries: List[VocabEntry]) -> List[VocabEntry]:
    """Descarga masiva de textos. Volvemos a 12 workers para máxima velocidad."""
    total = len(entries)
    enriched: List[VocabEntry] = []
    completed_count = 0

    def _update_ui(done: int, current_word: str):
        pct = int((done / total) * 100) if total else 0
        label = (
            f"AnkReader: Procesando {total} palabras...\n"
            f"Progreso: {done}/{total} ({pct}%)\n"
            f"Traduciendo: '{current_word}'"
        )
        if mw and hasattr(mw, "progress") and hasattr(mw, "taskman"):
            mw.taskman.run_on_main(lambda: mw.progress.update(label=label, value=done, max=total))

    _update_ui(0, "Iniciando descarga rápida...")

    # Volvemos a usar 12 hilos porque ahora solo consultamos diccionarios
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_enrich_entry, e): e for e in entries}
        for fut in as_completed(futures):
            entry_orig = futures[fut]
            try:
                enriched.append(fut.result())
            except Exception as exc:
                enriched.append(entry_orig)
            completed_count += 1
            _update_ui(completed_count, entry_orig.word)

    return enriched

def _background_task(col) -> List[VocabEntry]:
    db_path = find_vocab_db()
    if db_path is None: return []

    cfg = _get_config()
    since = cfg.get("last_sync_timestamp", 0)
    raw = fetch_new_entries(db_path, since)
    if not raw: return []

    deduped = {}
    for e in raw:
        key = (e.word.strip().lower(), e.book_title.strip())
        deduped[key] = e
    entries_to_process = list(deduped.values())

    return _enrich_all(entries_to_process)


def _on_success(entries: List[VocabEntry]) -> None:
    if not entries:
        tooltip("AnkReader: No se encontraron nuevas palabras en el Kindle.", parent=mw)
        return

    total = len(entries)
    added = 0
    skipped = 0

    for i, entry in enumerate(entries, 1):
        if mw and hasattr(mw, "progress"):
            mw.progress.update(
                label=f"AnkReader: Creando tarjetas...\n{i}/{total}",
                value=i, max=total
            )

        find_and_reset_existing_cards(entry.word)
        
        # Ahora add_vocab_note nos devuelve el ID de la carta
        note_id = add_vocab_note(entry)
        
        if note_id > 0:
            added += 1
            # Enviamos el ID y la palabra a la cola silenciosa de imágenes
            IMAGE_QUEUE.put((note_id, entry.word))
        else:
            skipped += 1

    newest_ts = max(e.timestamp for e in entries)
    update_last_sync(newest_ts)
    mw.reset()

    showInfo(
        f"<b>Sincronización rápida completada.</b>\n\n"
        f"✅ Tarjetas nuevas añadidas: {added}\n"
        f"⏭️ Duplicados omitidos: {skipped}\n\n"
        f"<i>Nota: Las {added} imágenes se están descargando en segundo plano. "
        f"Irán apareciendo en tus cartas durante los próximos minutos.</i>",
        title="AnkReader",
    )


def run_kindle_sync() -> None:
    db_path = find_vocab_db()
    if db_path is None:
        showWarning("No se encontró Kindle.", title="AnkReader")
        return

    op = QueryOp(parent=mw, op=_background_task, success=_on_success)
    op.with_progress(label="Conectando con el Kindle…").run_in_background()