# main.py (versione con logica di ricerca flessibile)

import sys
import time
import requests
import io
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer, QRect
from PyQt6.QtGui import QGuiApplication, QPixmap, QCursor
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

# Importa la tua UI
from ui import FinestraOverlay

# --- CLASSE PER GESTIRE IL DOWNLOAD DELLE COPERTINE (ORA FLESSIBILE) ---
class CoverDownloader(QObject):
    cover_ready = pyqtSignal(int, QPixmap, float)
    
    def __init__(self):
        super().__init__()
        self.last_track = {0: None, 1: None}
    
    def download_cover(self, deck_number, artist, title, album=None):
        # L'ID univoco si basa su artista e titolo, i dati minimi garantiti
        track_id = f"{artist}-{title}"
        if not artist or not title or self.last_track.get(deck_number) == track_id:
            return
        self.last_track[deck_number] = track_id
        
        thread = threading.Thread(
            target=self._download_worker,
            args=(deck_number, artist, title, album)
        )
        thread.daemon = True
        thread.start()
    
    def _download_worker(self, deck_number, artist, title, album):
        try:
            params = {}
            # --- LOGICA DI RICERCA FLESSIBILE ---
            # Se abbiamo l'album, la priorità è cercare quello.
            if artist and album:
                search_query = f"{artist} {album}"
                params = {'term': search_query, 'media': 'music', 'entity': 'album', 'limit': 1}
                print(f"Ricerca PRIORITARIA per ALBUM: '{search_query}'")
            # Altrimenti, ripieghiamo sulla ricerca per canzone (artista + titolo).
            elif artist and title:
                search_query = f"{artist} {title}"
                params = {'term': search_query, 'media': 'music', 'entity': 'song', 'limit': 1}
                print(f"Ricerca FALLBACK per CANZONE: '{search_query}'")
            # Se non abbiamo neanche i dati minimi, non facciamo nulla.
            else:
                return

            url = "https://itunes.apple.com/search"
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            cover_url = None
            duration_ms = 0
            if data.get('results'):
                result = data['results'][0]
                cover_url = result.get('artworkUrl100', '').replace('100x100', '600x600')
                # La durata è disponibile solo se abbiamo cercato per 'song'
                if params.get('entity') == 'song':
                    duration_ms = result.get('trackTimeMillis', 0)

            if not cover_url:
                print(f"Copertina non trovata per: {search_query}")
                return

            img_response = requests.get(cover_url, timeout=5)
            img_response.raise_for_status()
            img_data = img_response.content
            
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            
            duration_seconds = duration_ms / 1000.0
            self.cover_ready.emit(deck_number, pixmap, duration_seconds)
            
        except Exception as e:
            print(f"Errore durante il download della copertina: {e}")

# --- THREAD PER IL SERVER OSC ---
class OSCServerThread(QObject):
    deck_title_signal = pyqtSignal(int, str)
    deck_artist_signal = pyqtSignal(int, str)
    deck_album_signal = pyqtSignal(int, str)
    deck_time_signal = pyqtSignal(int, float)
    bpm_signal = pyqtSignal(float)
    beat_signal = pyqtSignal(int)
    request_cover = pyqtSignal(int, str, str, str)

    def __init__(self, ip="127.0.0.1", port=7000):
        super().__init__()
        self.ip = ip
        self.port = port
        self.server = None
        
        self.track_info = {
            0: {'title': '', 'artist': '', 'album': ''},
            1: {'title': '', 'artist': '', 'album': ''}
        }
        self.last_requested_track = {0: None, 1: None}

    def run(self):
        dispatcher = Dispatcher()
        # Mappature...
        dispatcher.map("/track/0/title", lambda addr, *args: self.handle_title(0, addr, *args))
        dispatcher.map("/track/0/artist", lambda addr, *args: self.handle_artist(0, addr, *args))
        dispatcher.map("/track/0/album", lambda addr, *args: self.handle_album(0, addr, *args))
        dispatcher.map("/time/0", lambda addr, *args: self.handle_time(0, addr, *args))
        dispatcher.map("/track/1/title", lambda addr, *args: self.handle_title(1, addr, *args))
        dispatcher.map("/track/1/artist", lambda addr, *args: self.handle_artist(1, addr, *args))
        dispatcher.map("/track/1/album", lambda addr, *args: self.handle_album(1, addr, *args))
        dispatcher.map("/time/1", lambda addr, *args: self.handle_time(1, addr, *args))
        dispatcher.map("/bpm/master/current", self.handle_bpm)
        dispatcher.map("/beat/master", self.handle_beat)
        
        self.server = BlockingOSCUDPServer((self.ip, self.port), dispatcher)
        print(f"Server OSC in ascolto su {self.ip}:{self.port}")
        self.server.serve_forever()

    def stop(self):
        if self.server: self.server.shutdown()

    # --- CONTROLLO CORRETTO PER DATI MINIMI (ARTISTA + TITOLO) ---
    def _check_and_request_cover(self, deck):
        info = self.track_info[deck]
        artist = info.get('artist')
        title = info.get('title')

        # Condizione minima per partire: ARTISTA e TITOLO
        if not artist or not title:
            return

        current_track_id = f"{artist} - {title}"
        if self.last_requested_track.get(deck) == current_track_id:
            return
        
        print(f"Dati minimi presenti (artista+titolo). Avvio richiesta download per Deck {deck}.")
        # Passiamo tutti i dati che abbiamo. Il downloader deciderà la strategia migliore.
        self.request_cover.emit(deck, artist, title, info.get('album', ''))
        self.last_requested_track[deck] = current_track_id

    def handle_title(self, deck, address, *args):
        if not args: return
        title = str(args[0])
        if title != self.track_info[deck].get('title'):
            print(f"Nuova traccia rilevata su Deck {deck}: '{title}'. Reset info.")
            self.track_info[deck] = {'title': title, 'artist': '', 'album': ''}
            self.last_requested_track[deck] = None
            self.deck_title_signal.emit(deck, title)
            self.deck_artist_signal.emit(deck, "")
            self.deck_album_signal.emit(deck, "")
        self._check_and_request_cover(deck)

    def handle_artist(self, deck, address, *args):
        if not args: return
        artist = str(args[0])
        self.track_info[deck]['artist'] = artist
        self.deck_artist_signal.emit(deck, artist)
        self._check_and_request_cover(deck)

    def handle_album(self, deck, address, *args):
        if not args: return
        album = str(args[0])
        self.track_info[deck]['album'] = album
        self.deck_album_signal.emit(deck, album)
        self._check_and_request_cover(deck)

    def handle_time(self, deck, address, *args):
        if args: self.deck_time_signal.emit(deck, float(args[0]))
    def handle_bpm(self, address, *args):
        if args: self.bpm_signal.emit(float(args[0]))
    def handle_beat(self, address, *args):
        if args: self.beat_signal.emit(int(args[0]))

# --- FUNZIONE MAIN (INVARIATA) ---
def main():
    app = QApplication(sys.argv)
    finestra = FinestraOverlay()

    HOT_ZONE_HEIGHT = 15
    primary_screen = QGuiApplication.primaryScreen().geometry()
    hot_zone = QRect(
        primary_screen.x(), primary_screen.y(),
        primary_screen.width(), HOT_ZONE_HEIGHT
    )

    def check_mouse_position():
        if not finestra.isVisible() and hot_zone.contains(QCursor.pos()):
            finestra.show()
            finestra.raise_()

    mouse_check_timer = QTimer()
    mouse_check_timer.setInterval(100)
    mouse_check_timer.timeout.connect(check_mouse_position)
    mouse_check_timer.start()

    cover_downloader = CoverDownloader()
    osc_thread = QThread()
    osc_server = OSCServerThread()
    osc_server.moveToThread(osc_thread)
    
    osc_server.deck_title_signal.connect(finestra.update_deck_title)
    osc_server.deck_artist_signal.connect(finestra.update_deck_artist)
    osc_server.deck_album_signal.connect(finestra.update_deck_album)
    osc_server.deck_time_signal.connect(finestra.update_deck_time)
    osc_server.bpm_signal.connect(finestra.update_bpm)
    osc_server.beat_signal.connect(finestra.update_beat)
    osc_server.request_cover.connect(cover_downloader.download_cover)
    cover_downloader.cover_ready.connect(finestra.update_deck_cover)
    
    osc_thread.started.connect(osc_server.run)
    osc_thread.start()

    def cleanup():
        print("Chiusura in corso...")
        osc_server.stop()
        osc_thread.quit()
        osc_thread.wait()

    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()