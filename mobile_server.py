import threading
import urllib.parse
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

from aqt import mw
from aqt.utils import tooltip
from .kindle_sync import VocabEntry, _get_config
from .sync_manager import _enrich_entry, IMAGE_QUEUE
from .note_creator import add_vocab_note, find_and_reset_existing_cards

PORT = 8080

class WordReceiverHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Escucha las peticiones GET desde el móvil."""
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        
        if 'word' in query:
            raw_text = query['word'][0].strip()
            
            # 1. Eliminar cualquier URL del texto
            text_no_urls = re.sub(r'https?://\S+', '', raw_text)
            
            # 2. Extraer solo la palabra (letras y guiones), ignorando comillas
            match = re.search(r'[A-Za-z\-]+', text_no_urls)
            
            if not match:
                print(f"[AnkReader/Mobile] No se encontró palabra válida en: '{raw_text}'")
                self.send_response(400)
                self.end_headers()
                return
                
            word = match.group(0).lower()
            print(f"[AnkReader/Mobile] Recibido: '{raw_text}' -> Limpio: '{word}'")
            
            # Leer el archivo de configuración para ver si mostramos el aviso
            cfg = _get_config()
            show_notif = cfg.get("show_mobile_notifications", True)
            
            if show_notif:
                mw.taskman.run_on_main(lambda: tooltip(f"📱 Recibiendo: {word}"))
            
            # Respondemos al móvil rápido con un 200 OK
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
            
            
            # Enriquecemos la palabra (DeepL, fonética, audio)
            entry = VocabEntry(word=word, book_title="", usage="", timestamp=0)
            enriched_entry = _enrich_entry(entry)
            
            # Pasamos la creación de la carta al hilo principal de Anki
            def _create_note_ui():
                find_and_reset_existing_cards(word)
                note_id = add_vocab_note(enriched_entry, deck_name="Manual Vocabulary")
                if note_id > 0:
                    IMAGE_QUEUE.put((note_id, word))
                    print(f"[AnkReader/Mobile] '{word}' añadida con éxito.")
                    if show_notif:
                        tooltip(f"✅ '{word}' guardada. Descargando imagen...")
                    
            mw.taskman.run_on_main(_create_note_ui)
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def _start_server():
    try:
        server = HTTPServer(('', PORT), WordReceiverHandler)
        print(f"[AnkReader/Mobile] Servidor escuchando en el puerto {PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"[AnkReader/Mobile] Error iniciando servidor: {e}")

_server_thread = threading.Thread(target=_start_server, daemon=True)
_server_thread.start()