# main.py (versione con logica di ricerca flessibile)

import sys
import time
import requests
import io
import threading
import configparser
import base64
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer, QRect
from PyQt6.QtGui import QGuiApplication, QPixmap, QCursor
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

# Importa la tua UI
from ui import FinestraOverlay, SettingsDialog

# --- GESTORE IMPOSTAZIONI ---
class SettingsManager:
    def __init__(self, filename="config.ini"):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.defaults = {
            'osc': {
                'ip': '127.0.0.1',
                'port': '7000',
                'resolume_ip': '127.0.0.1',
                'resolume_port': '7001'
            },
            'osc_paths': {
                'deck1_title': '/track/0/title',
                'deck1_artist': '/track/0/artist',
                'deck1_album': '/track/0/album',
                'deck1_time': '/time/0',
                'deck2_title': '/track/1/title',
                'deck2_artist': '/track/1/artist',
                'deck2_album': '/track/1/album',
                'deck2_time': '/time/1',
                'bpm': '/bpm/master/current',
                'beat': '/beat/master',
                'resolume_bpm': '/composition/tempocontroller/tempo'
            },
            'spotify': {
                'client_id': 'IL_TUO_CLIENT_ID',
                'client_secret': 'IL_TUO_CLIENT_SECRET'
            }
        }
        self.load()

    def load(self):
        if not self.config.read(self.filename):
            print("File config.ini non trovato. Creazione con valori predefiniti.")
            self.config.read_dict(self.defaults)
            self.save()
        # Assicura che tutte le sezioni e chiavi predefinite esistano
        for section, keys in self.defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
            for key, value in keys.items():
                if not self.config.has_option(section, key):
                    self.config.set(section, key, value)
        self.save() # Salva eventuali chiavi mancanti

    def get(self, section, key):
        return self.config.get(section, key, fallback=self.defaults.get(section, {}).get(key))

    def get_section(self, section):
        return dict(self.config.items(section))

    def save(self):
        with open(self.filename, 'w') as configfile:
            self.config.write(configfile)

    def update_from_dict(self, settings_dict):
        self.config.read_dict(settings_dict)
        self.save()

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
    
    def _search_itunes(self, artist, title, album):
        """Tenta di trovare la traccia su iTunes. Restituisce (cover_url, duration_seconds)."""
        print(f"Ricerca su iTunes per: '{artist} - {title}'")
        search_query = f"{artist} {title}"
        if album:
            search_query += f" {album}"
        
        params = {'term': search_query, 'media': 'music', 'entity': 'song', 'limit': 1}
        url = "https://itunes.apple.com/search"
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get('results'):
            result = data['results'][0]
            cover_url = result.get('artworkUrl100', '').replace('100x100', '600x600')
            duration_ms = result.get('trackTimeMillis', 0)
            print("Trovato su iTunes.")
            return cover_url, duration_ms / 1000.0
        
        print("Non trovato su iTunes.")
        return None, 0

    def _search_deezer(self, artist, title, album):
        """Tenta di trovare la traccia su Deezer. Restituisce (cover_url, duration_seconds)."""
        print(f"Fallback: ricerca su Deezer per: '{artist} - {title}'")
        # La query di Deezer è più efficace con le virgolette
        query = f'artist:"{artist}" track:"{title}"'
        
        params = {'q': query, 'limit': 1}
        url = "https://api.deezer.com/search"
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get('data'):
            result = data['data'][0]
            # Deezer fornisce URL per diverse dimensioni, prendiamo la più grande
            album_info = result.get('album', {})
            cover_url = album_info.get('cover_xl') or album_info.get('cover_big')
            duration = result.get('duration', 0)
            print("Trovato su Deezer.")
            return cover_url, float(duration)

        print("Non trovato su Deezer.")
        return None, 0

    def _download_worker(self, deck_number, artist, title, album):
        cover_url, duration_seconds = None, 0
        try:
            # 1. Prova con iTunes
            cover_url, duration_seconds = self._search_itunes(artist, title, album)
            
            # 2. Se iTunes fallisce, prova con Deezer (fallback)
            if not cover_url:
                cover_url, duration_seconds = self._search_deezer(artist, title, album)
        
        except Exception as e:
            print(f"Errore durante la ricerca della copertina: {e}")
        
        # 3. Se abbiamo trovato una copertina, scaricala
        try:
            if not cover_url: return
            img_response = requests.get(cover_url, timeout=5)
            img_response.raise_for_status()
            img_data = img_response.content
            
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            self.cover_ready.emit(deck_number, pixmap, duration_seconds)
        except Exception as e:
            print(f"Errore durante il download dell'immagine da {cover_url}: {e}")

# --- THREAD PER IL SERVER OSC ---
class OSCServerThread(QObject):
    deck_title_signal = pyqtSignal(int, str)
    deck_artist_signal = pyqtSignal(int, str)
    deck_album_signal = pyqtSignal(int, str)
    deck_time_signal = pyqtSignal(int, float)
    bpm_signal = pyqtSignal(float)
    beat_signal = pyqtSignal(int)
    request_cover = pyqtSignal(int, str, str, str)

    def __init__(self, settings_manager):
        super().__init__()
        self.settings = settings_manager
        self.ip = self.settings.get('osc', 'ip')
        self.port = int(self.settings.get('osc', 'port'))
        self.server = None
        
        resolume_ip = self.settings.get('osc', 'resolume_ip')
        resolume_port = int(self.settings.get('osc', 'resolume_port'))
        # Client OSC per inviare dati a Resolume (o altro)
        self.resolume_client = SimpleUDPClient(resolume_ip, resolume_port)
        
        self.track_info = {
            0: {'title': '', 'artist': '', 'album': ''},
            1: {'title': '', 'artist': '', 'album': ''}
        }
        self.last_requested_track = {0: None, 1: None}

    def run(self):
        dispatcher = Dispatcher()
        paths = self.settings.get_section('osc_paths')
        
        dispatcher.map(paths['deck1_title'], lambda addr, *args: self.handle_title(0, addr, *args))
        dispatcher.map(paths['deck1_artist'], lambda addr, *args: self.handle_artist(0, addr, *args))
        dispatcher.map(paths['deck1_album'], lambda addr, *args: self.handle_album(0, addr, *args))
        dispatcher.map(paths['deck1_time'], lambda addr, *args: self.handle_time(0, addr, *args))
        dispatcher.map(paths['deck2_title'], lambda addr, *args: self.handle_title(1, addr, *args))
        dispatcher.map(paths['deck2_artist'], lambda addr, *args: self.handle_artist(1, addr, *args))
        dispatcher.map(paths['deck2_album'], lambda addr, *args: self.handle_album(1, addr, *args))
        dispatcher.map(paths['deck2_time'], lambda addr, *args: self.handle_time(1, addr, *args))
        dispatcher.map(paths['bpm'], self.handle_bpm)
        dispatcher.map(paths['beat'], self.handle_beat)
        
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
        if args: 
            self.deck_time_signal.emit(deck, float(args[0]))
            print(f"\n{time.strftime('%H:%M:%S')} - Deck {deck} Time: {args[0]}s")
    def handle_bpm(self, address, *args):
        if args: self.bpm_signal.emit(float(args[0]))
        if args:
            bpm = float(args[0])
            # Emetti il segnale per aggiornare la UI
            self.bpm_signal.emit(bpm)
            # Inoltra il BPM a Resolume sulla porta 7001
            resolume_path = self.settings.get('osc_paths', 'resolume_bpm')
            bpmr = (bpm -20 )*0.002083
            self.resolume_client.send_message(resolume_path, bpmr)
            print(f"Inoltrato BPM: {bpm} a {self.resolume_client.address}:{self.resolume_client.port} su path {resolume_path}")
    def handle_beat(self, address, *args):
        if args: self.beat_signal.emit(int(args[0]))

# --- FUNZIONE MAIN ---
def main():
    app = QApplication(sys.argv)
    settings_manager = SettingsManager()

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

    # --- GESTIONE THREAD OSC ---
    osc_thread = QThread()
    osc_server = OSCServerThread(settings_manager)
    osc_server.moveToThread(osc_thread)

    def start_osc_server():
        if not osc_thread.isRunning():
            osc_thread.started.connect(osc_server.run)
            osc_thread.start()

    def stop_osc_server():
        if osc_thread.isRunning():
            osc_server.stop()
            osc_thread.quit()
            osc_thread.wait()

    def restart_osc_server():
        print("Riavvio del server OSC con le nuove impostazioni...")
        stop_osc_server()
        # Ricrea l'istanza del server con le nuove impostazioni
        nonlocal osc_server
        osc_server = OSCServerThread(settings_manager)
        osc_server.moveToThread(osc_thread)
        connect_signals() # Riconnetti i segnali alla nuova istanza
        start_osc_server()
        print("Server OSC riavviato.")

    # --- GESTIONE FINESTRA IMPOSTAZIONI ---
    def open_settings():
        # Crea un dizionario completo delle impostazioni attuali
        current_settings = {
            'osc': settings_manager.get_section('osc'),
            'osc_paths': settings_manager.get_section('osc_paths'),
            'spotify': settings_manager.get_section('spotify')
        }
        dialog = SettingsDialog(current_settings, finestra)
        dialog.settings_saved.connect(on_settings_saved)
        dialog.exec()

    def on_settings_saved(new_settings):
        settings_manager.update_from_dict(new_settings)
        restart_osc_server()

    # --- COLLEGAMENTO SEGNALI ---
    cover_downloader = CoverDownloader()
    def connect_signals():
        osc_server.deck_title_signal.connect(finestra.update_deck_title)
        osc_server.deck_artist_signal.connect(finestra.update_deck_artist)
        osc_server.deck_album_signal.connect(finestra.update_deck_album)
        osc_server.deck_time_signal.connect(finestra.update_deck_time)
        osc_server.bpm_signal.connect(finestra.update_bpm)
        osc_server.beat_signal.connect(finestra.update_beat)
        osc_server.request_cover.connect(cover_downloader.download_cover)
    
    connect_signals()
    cover_downloader.cover_ready.connect(finestra.update_deck_cover)
    finestra.open_settings_requested.connect(open_settings)
    
    start_osc_server()
    app.aboutToQuit.connect(stop_osc_server)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()