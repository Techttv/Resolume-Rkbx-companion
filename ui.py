# ui.py (versione corretta e più robusta)

import sys
from functools import partial
from datetime import timedelta
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QStyleFactory, QHBoxLayout, QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QScrollArea
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QStyleFactory, QHBoxLayout, QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QScrollArea, QStyle
from PyQt6.QtCore import Qt, QRect, pyqtSlot, QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap, QKeyEvent, QPainter, QColor, QFontDatabase, QFont, QCursor, QPainterPath, QIcon

class FinestraOverlay(QWidget):
    open_settings_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        # Abilita il tracking del mouse per ricevere leaveEvent in modo affidabile
        self.setMouseTracking(True)
        
        # Dati delle tracce
        self.track_data = {
            0: {'current_time': -1, 'duration': 0, 'title': '', 'artist': '', 'album': ''},
            1: {'current_time': -1, 'duration': 0, 'title': '', 'artist': '', 'album': ''}
        }
        
        # Timer per aggiornare il tempo rimanente
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time_display)
        self.time_timer.start(100)  # Aggiorna ogni 100ms
        
        self.setup_window_flags()
        self.setup_ui()
        self.setup_stylesheet()
        self.centra_in_alto()
        self.hide()  # La finestra parte nascosta

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            QGuiApplication.quit()
        elif event.key() == Qt.Key.Key_F1:
            self.open_settings_requested.emit()
        else:
            super().keyPressEvent(event)
            
    def leaveEvent(self, event):
        """
        Questo metodo viene chiamato automaticamente da Qt quando il cursore
        del mouse esce dall'area della finestra.
        """
        self.hide()
        super().leaveEvent(event)

    def setup_window_flags(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def setup_ui(self):
        self.layout_principale = QHBoxLayout()
        self.setLayout(self.layout_principale)
        
        self.setup_primo_deck()
        self.setup_centrale()
        self.setup_secondo_deck()
        
        self.layout_principale.setStretchFactor(self.primodeck, 4)
        self.layout_principale.setStretchFactor(self.centrale, 1)
        self.layout_principale.setStretchFactor(self.secondodeck, 4)
        
    def setup_primo_deck(self):
        self.primo_immagine = QLabel()
        self.primo_titolo = QLabel("In attesa...")
        self.primo_artista = QLabel("")
        self.primo_durata = QLabel("--:--")
        self.primo_fine = QLabel("--:--")

        self.cover = QPixmap(160, 160)
        self.cover.fill(QColor(40, 40, 40))
        
        self.primo_immagine.setPixmap(self.cover)
        self.primo_immagine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.primo_immagine.setFixedSize(160, 160)
        
        self.primo_titolo.setObjectName("deck_title")
        self.primo_artista.setObjectName("deck_artist")
        self.primo_durata.setObjectName("time_label")
        self.primo_fine.setObjectName("time_label")
        
        self.primodeck = QHBoxLayout()
        primo_info = QVBoxLayout()
        primo_realtime = QHBoxLayout()
        
        primo_info.addWidget(self.primo_titolo)
        primo_info.addWidget(self.primo_artista)
        primo_info.addStretch()

        primo_realtime.addWidget(self.primo_durata)
        primo_realtime.addStretch()
        primo_realtime.addWidget(self.primo_fine)
        
        primo_info.addLayout(primo_realtime)
        
        self.primodeck.addWidget(self.primo_immagine)
        self.primodeck.addLayout(primo_info)
        
        self.layout_principale.addLayout(self.primodeck)
        
    def setup_centrale(self):
        self.centrale_bpm = QLabel("--- BPM")
        self.centrale_beat = QLabel("")
        self.centrale_status = CircleLabel(size=20, color=QColor(255, 60, 60))


        self.centrale_bpm.setObjectName("bpm_label")
        self.centrale_beat.setObjectName("beat_label")
        self.centrale_bpm.setMinimumWidth(150)
        self.centrale_bpm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.centrale_beat.setAlignment(Qt.AlignmentFlag.AlignCenter)


        self.centrale = QVBoxLayout()
        self.centrale.addWidget(self.centrale_bpm)
        self.centrale.addWidget(self.centrale_beat)
        self.centrale.addWidget(self.centrale_status, alignment=Qt.AlignmentFlag.AlignCenter)
        self.layout_principale.addLayout(self.centrale)
        
    def setup_secondo_deck(self):
        self.secondo_immagine = QLabel()
        self.secondo_titolo = QLabel("In attesa...")
        self.secondo_artista = QLabel("")
        self.secondo_durata = QLabel("--:--")
        self.secondo_fine = QLabel("--:--")

        self.cover2 = QPixmap(160, 160)
        self.cover2.fill(QColor(40, 40, 40))

        self.secondo_titolo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.secondo_artista.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.secondo_titolo.setObjectName("deck_title")
        self.secondo_artista.setObjectName("deck_artist")
        self.secondo_durata.setObjectName("time_label")
        self.secondo_fine.setObjectName("time_label")

        self.secondo_immagine.setPixmap(self.cover2)
        self.secondo_immagine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.secondo_immagine.setFixedSize(160, 160)

        self.secondodeck = QHBoxLayout()
        secondo_info = QVBoxLayout()
        secondo_realtime = QHBoxLayout()
        
        secondo_info.addWidget(self.secondo_titolo)
        secondo_info.addWidget(self.secondo_artista)
        secondo_info.addStretch()

        secondo_realtime.addWidget(self.secondo_fine)
        secondo_realtime.addStretch()
        secondo_realtime.addWidget(self.secondo_durata)       
        
        secondo_info.addLayout(secondo_realtime)

        self.secondodeck.addLayout(secondo_info)
        self.secondodeck.addWidget(self.secondo_immagine)
        
        self.layout_principale.addLayout(self.secondodeck)

    def setup_stylesheet(self):
        default_stylesheet = """
        
        """
        try:
            with open("stylesheet.css", 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print("File stylesheet.css non trovato, uso stile predefinito")
            self.setStyleSheet(default_stylesheet)

    def centra_in_alto(self):
        larghezza_finestra = 1400
        altezza_finestra = 180
        self.setFixedSize(larghezza_finestra, altezza_finestra)

        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        dati_schermo = screen.geometry()
        
        x = dati_schermo.x() + (dati_schermo.width() - larghezza_finestra) // 2
        y = dati_schermo.y()
        self.move(x, y)

    def format_time(self, seconds):
        if not isinstance(seconds, (int, float)) or seconds < 0:
            return "--:--"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def update_time_display(self):
        """Aggiorna il display del tempo per entrambi i deck in modo robusto."""
        for deck in [0, 1]:
            data = self.track_data[deck]
            
            # 1. Formatta il tempo corrente. Mostra "--:--" se non valido.
            current_time_str = self.format_time(data['current_time'])
            
            # 2. Calcola e formatta il tempo rimanente.
            #    È possibile solo se abbiamo una durata valida (> 0) e un tempo corrente valido.
            remaining_time_str = "--:--"
            if data['duration'] > 0 and data['current_time'] >= 0:
                remaining = data['duration'] - data['current_time']
                # Assicura che il tempo rimanente non sia negativo
                remaining = max(0, remaining) 
                remaining_time_str = f"-{self.format_time(remaining)}"
                
            # 3. Assegna le stringhe formattate alle etichette corrette
            if deck == 0:
                self.primo_durata.setText(current_time_str)
                self.primo_fine.setText(remaining_time_str)
            else:
                self.secondo_durata.setText(current_time_str)
                self.secondo_fine.setText(remaining_time_str)

    @pyqtSlot(int, str)
    def update_deck_title(self, deck, title):
        self.track_data[deck]['title'] = title
        if deck == 0:
            self.primo_titolo.setText(title if title else "In attesa...")
        else:
            self.secondo_titolo.setText(title if title else "In attesa...")
        
        # Reset dei dati temporali quando cambia la traccia
        self.track_data[deck]['current_time'] = -1
        self.track_data[deck]['duration'] = 0

    @pyqtSlot(int, str)
    def update_deck_artist(self, deck, artist):
        self.track_data[deck]['artist'] = artist
        if deck == 0:
            self.primo_artista.setText(artist)
        else:
            self.secondo_artista.setText(artist)

    @pyqtSlot(int, str)
    def update_deck_album(self, deck, album):
        self.track_data[deck]['album'] = album

    @pyqtSlot(int, float)
    def update_deck_time(self, deck, current_time):
        self.track_data[deck]['current_time'] = current_time

    @pyqtSlot(int, QPixmap, float)
    def update_deck_cover(self, deck, pixmap, duration):
        self.track_data[deck]['duration'] = duration
        
        if not pixmap.isNull():
            pixmap_scaled = pixmap.scaled(
                160, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            if deck == 0:
                self.primo_immagine.setPixmap(pixmap_scaled)
            else:
                self.secondo_immagine.setPixmap(pixmap_scaled)

    @pyqtSlot(float)
    def update_bpm(self, bpm):
        self.centrale_bpm.setText(f"{bpm:.1f} BPM")
        if bpm > 0:
            self.centrale_status.set_color(QColor(0, 255, 100))
        else:
            self.centrale_status.set_color(QColor(255, 60, 60))

    @pyqtSlot(int)
    def update_beat(self, beat):
        beat+=1  # Perché i beat partono da 0
        self.centrale_beat.setText(f"{beat}")
        if beat == 1:
            self.centrale_status.pulse()


class CircleLabel(QLabel):
    def __init__(self, size=30, color=Qt.GlobalColor.green):
        super().__init__()
        self.size = size
        self.base_color = color
        self.color = color
        self.setFixedSize(size, size)
        
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self.reset_color)
        self.pulse_timer.setSingleShot(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect())

    def set_color(self, color):
        self.base_color = color
        self.color = color
        self.update()

    def pulse(self):
        self.color = QColor(255, 255, 255)
        self.update()
        self.pulse_timer.start(100)
    
    def reset_color(self):
        self.color = self.base_color
        self.update()

class SettingsDialog(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni")
        self.setMinimumSize(500, 400)
        self.settings = settings
        self.line_edits = {}

        layout = QVBoxLayout(self)

        # Area scrollabile per contenere tutte le impostazioni
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        container = QWidget()
        form_layout = QFormLayout(container)
        
        # Sezione OSC
        form_layout.addRow(self.create_section_label("Server OSC"))
        self.add_setting_row(form_layout, "osc", "ip", "Indirizzo IP")
        self.add_setting_row(form_layout, "osc", "port", "Porta")

        # Sezione Path OSC
        form_layout.addRow(self.create_section_label("Percorsi OSC"))
        for key in self.settings.get('osc_paths', {}):
            self.add_setting_row(form_layout, "osc_paths", key, f"Path: {key}")

        # Sezione Spotify
        form_layout.addRow(self.create_section_label("Spotify API"))
        self.add_setting_row(form_layout, "spotify", "client_id", "Client ID")
        self.add_setting_row(form_layout, "spotify", "client_secret", "Client Secret")

        scroll_area.setWidget(container)

        # Pulsanti Salva/Annulla
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def create_section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        return label

    def add_setting_row(self, layout, section, key, label_text):
        value = self.settings.get(section, {}).get(key, "")
        line_edit = QLineEdit(str(value))
        layout.addRow(label_text, line_edit)
        self.line_edits[(section, key)] = line_edit

    def accept(self):
        # Aggiorna il dizionario delle impostazioni con i nuovi valori
        for (section, key), line_edit in self.line_edits.items():
            if section not in self.settings: self.settings[section] = {}
            self.settings[section][key] = line_edit.text()
        self.settings_saved.emit(self.settings)
        super().accept()