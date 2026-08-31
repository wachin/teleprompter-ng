"""
ui.py — Clase principal del Teleprompter con PyQt6.
Fase 1: Cuenta regresiva, progreso, selector de guion, línea guía.

Fase 0 (auditoría):
- Modo espejo con transformación visual real (QTransform), no RTL.
- Sincronización de voz: los callbacks del hilo de audio llegan aquí
  y se aplican en el hilo principal de Qt mediante señales.
- El servidor remoto se detiene correctamente al cerrar la ventana.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QTextEdit, QVBoxLayout, QWidget, QLabel,
    QHBoxLayout, QFrame, QProgressBar, QFileDialog, QDialog,
    QVBoxLayout as DialogLayout, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QUrl, QSize, QObject, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QTextCursor, QKeySequence, QShortcut, QPixmap,
    QImage,
)
from config import save_config
from logging_setup import get_logger
import os
import qrcode
from io import BytesIO

log = get_logger("UI")


class _SpeechSignals(QObject):
    """Señales para cruzar desde el hilo de audio al hilo de Qt."""
    status_changed = pyqtSignal(str)
    wpm_updated = pyqtSignal(float, float)
    speed_suggestion = pyqtSignal(int)


class MirrorView(QWidget):
    """
    Widget que pinta una copia reflejada horizontalmente de otro widget.

    Fase 0: QWidget no admite transformaciones visuales directas y
    QGraphicsProxyWidget no puede incrustar un widget que ya pertenece
    a un layout. La solución es renderizar el widget origen con grab()
    y dibujarlo espejado con QPainter. Se repinta cuando el scroll del
    origen cambia (el desplazamiento automático pasa por la barra).
    """

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self._source = source
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        # Sin una política expansiva el layout colapsa este widget a 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        source.verticalScrollBar().valueChanged.connect(self.update)

    def set_source(self, source):
        """Cambia el widget que se refleja."""
        if self._source is not None:
            try:
                self._source.verticalScrollBar().valueChanged.disconnect(self.update)
            except TypeError:
                pass
        self._source = source
        if source is not None:
            source.verticalScrollBar().valueChanged.connect(self.update)
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter

        if self._source is None:
            return
        pixmap = self._source.grab()
        painter = QPainter(self)
        # Reflejo horizontal: trasladar el origen al borde derecho y
        # invertir el eje X.
        painter.translate(self.width(), 0)
        painter.scale(-1, 1)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()


class Teleprompter(QMainWindow):
    def __init__(self, text, config, script_path=None):
        super().__init__()
        self.config = config
        self.text_content = text
        self.script_path = script_path
        self.total_words = len(text.split())

        # Ventana
        self.setWindowTitle("Teleprompter Pro")
        self.setMinimumSize(800, 600)

        if config["fullscreen"]:
            try:
                self.showFullScreen()
            except:
                self.showMaximized()
        else:
            self.showMaximized()

        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Panel superior (barra de herramientas) ─────────────
        self.toolbar = QFrame()
        self.toolbar.setFixedHeight(45)
        self.toolbar.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 220);
                border-bottom: 1px solid #333;
            }
        """)
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(15, 5, 15, 5)

        # Botón de selector de guion
        self.script_label = QLabel("📄 " + (os.path.basename(script_path) if script_path else "Sin guion"))
        self.script_label.setStyleSheet("color: #AAA; font-size: 14px; background: transparent;")
        toolbar_layout.addWidget(self.script_label)

        self.open_btn = QLabel("  [O] Abrir guion")
        self.open_btn.setStyleSheet("color: #FFD700; font-size: 14px; background: transparent; font-weight: bold;")
        toolbar_layout.addWidget(self.open_btn)

        toolbar_layout.addStretch()

        # Palabras por minuto configurables
        self.wpm = config.get("wpm", 150)
        self.wpm_label = QLabel(f"WPM: {self.wpm}")
        self.wpm_label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        toolbar_layout.addWidget(self.wpm_label)

        toolbar_layout.addWidget(self._separator())

        # Indicador de sincronización de voz
        self.voice_sync_label = QLabel("🎤 V: Off")
        self.voice_sync_label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        toolbar_layout.addWidget(self.voice_sync_label)

        main_layout.addWidget(self.toolbar)

        # ── Área de texto con línea guía ───────────────────────
        text_container = QWidget()
        text_container.setStyleSheet(f"background-color: {config['bg_color']};")
        # Guardar referencia: el modo espejo intercambia widgets aquí
        self.text_layout = QVBoxLayout(text_container)
        self.text_layout.setContentsMargins(config["margin_x"], 0, config["margin_x"], 0)

        # Widget de texto
        self.text_widget = QTextEdit()
        self.text_widget.setReadOnly(True)
        self.text_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_widget.setStyleSheet(f"""
            QTextEdit {{
                background-color: {config['bg_color']};
                color: {config['text_color']};
                border: none;
                selection-background-color: {config['text_color']};
                selection-color: {config['bg_color']};
            }}
        """)

        # Configurar fuente
        self.font_family = config["font_family"]
        self.font_size = config["font_size"]
        self._update_font()

        # Insertar el guion
        self.text_widget.setPlainText(text)

        self.text_layout.addWidget(self.text_widget)
        main_layout.addWidget(text_container, 1)

        # ── Línea guía (horizontal en el centro) ───────────────
        self.guide_line = QFrame()
        self.guide_line.setFrameShape(QFrame.Shape.HLine)
        self.guide_line.setFixedHeight(2)
        self.guide_line.setStyleSheet("background-color: rgba(255, 215, 0, 80);")
        self.text_layout.addWidget(self.guide_line)

        # ── Panel inferior (progreso y controles) ──────────────
        self.bottom_panel = QFrame()
        self.bottom_panel.setFixedHeight(60)
        self.bottom_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 220);
                border-top: 1px solid #333;
            }
        """)
        bottom_layout = QHBoxLayout(self.bottom_panel)
        bottom_layout.setContentsMargins(15, 5, 15, 5)

        # Estado
        self.status_label = QLabel("⏸ Pausado")
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold; background: transparent;")
        bottom_layout.addWidget(self.status_label)

        # Separador
        bottom_layout.addWidget(self._separator())

        # Velocidad
        self.speed_label = QLabel(f"⚡ {config['scroll_speed']}")
        self.speed_label.setStyleSheet("color: #FFD700; font-size: 16px; font-weight: bold; background: transparent;")
        bottom_layout.addWidget(self.speed_label)

        bottom_layout.addWidget(self._separator())

        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #333;
                border: none;
                border-radius: 5px;
                text-align: center;
                color: white;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #FFD700;
                border-radius: 5px;
            }
        """)
        bottom_layout.addWidget(self.progress_bar, 1)

        bottom_layout.addWidget(self._separator())

        # Tiempo restante estimado
        self.time_label = QLabel("⏱ --:--")
        self.time_label.setStyleSheet("color: #AAA; font-size: 16px; background: transparent;")
        bottom_layout.addWidget(self.time_label)

        # Contador de palabras
        self.words_label = QLabel("📝 0 / " + str(self.total_words))
        self.words_label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        bottom_layout.addWidget(self.words_label)

        main_layout.addWidget(self.bottom_panel)

        # ── Variables de control ───────────────────────────────
        self.scroll_speed = config["scroll_speed"]
        self.is_running = False
        self.is_mirror = config["mirror_mode"]
        self._mirror_host = None  # Contenedor del reflejo (MirrorHost)
        self.countdown_active = False
        self.scroll_position = 0  # Posición en píxeles

        # Timer para el scroll
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self._scroll_step)

        # Timer para cuenta regresiva
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._countdown_step)
        self.countdown_value = 3

        # Timer para actualizar progreso
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.start(100)  # Actualizar cada 100ms

        # Aplicar espejo si está activado
        if self.is_mirror:
            self._apply_mirror()

        # Servidor remoto: desactivado por defecto (Fase 0).
        # Se activa con Q o desde show_qr_code().
        self.remote_server = None

        # Sincronización de voz
        self.speech_sync = None
        self.speech_sync_active = False
        # Señales que el hilo de audio usará para tocarnos con seguridad
        self._speech_signals = _SpeechSignals()
        self._speech_signals.status_changed.connect(self._on_sync_status_change)
        self._speech_signals.wpm_updated.connect(self._on_wpm_update)
        self._speech_signals.speed_suggestion.connect(self._apply_speed_suggestion)

    def _separator(self):
        """Crea un separador vertical."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(2)
        sep.setStyleSheet("background-color: #444;")
        return sep

    # ── Cuenta regresiva ───────────────────────────────────────

    def start_countdown(self):
        """Inicia la cuenta regresiva 3-2-1."""
        self.countdown_active = True
        self.countdown_value = 3
        self.status_label.setText("🔴 Preparado...")
        self.status_label.setStyleSheet("color: #FF4444; font-size: 16px; font-weight: bold; background: transparent;")
        self.countdown_timer.start(1000)  # 1 segundo

    def _countdown_step(self):
        """Paso de la cuenta regresiva."""
        if self.countdown_value > 0:
            self.status_label.setText(f"🔴 {self.countdown_value}")
            self.countdown_value -= 1
        else:
            self.countdown_timer.stop()
            self.countdown_active = False
            self.status_label.setText("▶ Reproduciendo")
            self.status_label.setStyleSheet("color: #44FF44; font-size: 16px; font-weight: bold; background: transparent;")
            self.is_running = True
            self._update_timer_interval()
            self.scroll_timer.start()

    # ── Controles ──────────────────────────────────────────────

    def toggle(self):
        """Play / Pausa con cuenta regresiva."""
        if self.countdown_active:
            # Cancelar cuenta regresiva
            self.countdown_timer.stop()
            self.countdown_active = False
            self.status_label.setText("⏸ Pausado")
            self.status_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold; background: transparent;")
            return

        if self.is_running:
            # Pausar
            self.is_running = False
            self.scroll_timer.stop()
            self.status_label.setText("⏸ Pausado")
            self.status_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold; background: transparent;")
        else:
            # Iniciar con cuenta regresiva
            self.start_countdown()

    def speed_up(self):
        """Aumentar velocidad."""
        self.scroll_speed += 1
        self._update_timer_interval()
        self.speed_label.setText(f"⚡ {self.scroll_speed}")

    def speed_down(self):
        """Disminuir velocidad."""
        if self.scroll_speed > 1:
            self.scroll_speed -= 1
            self._update_timer_interval()
            self.speed_label.setText(f"⚡ {self.scroll_speed}")

    def reset(self):
        """Volver al inicio del texto."""
        self.is_running = False
        self.countdown_active = False
        self.scroll_timer.stop()
        self.countdown_timer.stop()
        self.text_widget.verticalScrollBar().setValue(0)
        self.status_label.setText("⏸ Pausado")
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold; background: transparent;")

    def font_bigger(self):
        """Aumentar tamaño de fuente."""
        self.font_size += 2
        self._update_font()

    def font_smaller(self):
        """Disminuir tamaño de fuente."""
        if self.font_size > 10:
            self.font_size -= 2
            self._update_font()

    def toggle_fullscreen(self):
        """Alternar pantalla completa."""
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def open_script(self):
        """Abrir diálogo para seleccionar un guion."""
        from paths import script_dir as default_scripts_dir
        start_dir = (
            os.path.dirname(os.path.abspath(self.script_path))
            if self.script_path and os.path.exists(self.script_path)
            else default_scripts_dir()
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir guion",
            start_dir,
            "Archivos de texto (*.txt);;Todos los archivos (*)"
        )
        if file_path:
            self._load_script(os.path.abspath(file_path))

    def _load_script(self, path):
        """Carga un nuevo guion."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.text_content = text
            self.text_widget.setPlainText(text)
            self.total_words = len(text.split())
            self.script_path = path
            self.script_label.setText("📄 " + os.path.basename(path))
            self.reset()
            self.words_label.setText(f"📝 0 / {self.total_words}")
        except Exception as e:
            self.status_label.setText(f"❌ Error: {e}")

    def toggle_guide_line(self):
        """Mostrar/ocultar línea guía."""
        if self.guide_line.isVisible():
            self.guide_line.hide()
        else:
            self.guide_line.show()

    def toggle_speech_sync(self):
        """Activar/desactivar sincronización de voz."""
        if self.speech_sync_active:
            # Desactivar
            if self.speech_sync:
                self.speech_sync.stop()
            self.speech_sync_active = False
            self.voice_sync_label.setText("🎤 V: Off")
            self.voice_sync_label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        else:
            # Activar
            if not self.speech_sync:
                from speech_sync import SpeechSync
                self.speech_sync = SpeechSync(self)
                self.speech_sync.set_script(self.text_content)
                # Los callbacks emiten señales; la UI nunca se toca
                # desde el hilo de audio.
                self.speech_sync.on_wpm_update = self._speech_signals.wpm_updated.emit
                self.speech_sync.on_status_change = self._speech_signals.status_changed.emit
                self.speech_sync.on_speed_suggestion = self._speech_signals.speed_suggestion.emit

            if self.speech_sync.model:
                if self.speech_sync.start():
                    self.speech_sync_active = True
                    self.voice_sync_label.setText("🎤 V: On")
                    self.voice_sync_label.setStyleSheet("color: #44FF44; font-size: 14px; font-weight: bold; background: transparent;")
            else:
                log.warning("Modelo de voz no disponible. Colócalo en models/model-es")
                self.voice_sync_label.setText("🎤 V: Error")
                self.voice_sync_label.setStyleSheet("color: #FF4444; font-size: 14px; background: transparent;")
                self.status_label.setText("⚠️ Modelo de voz no encontrado (models/model-es)")

    def _on_wpm_update(self, current_wpm, target_wpm):
        """Callback cuando se actualiza el WPM (hilo principal de Qt)."""
        self.wpm_label.setText(f"WPM: {current_wpm:.0f}/{target_wpm}")

    def _on_sync_status_change(self, status):
        """Callback cuando cambia el estado de sincronización (hilo Qt)."""
        if status == "active":
            self.voice_sync_label.setText("🎤 V: Listening")
            self.voice_sync_label.setStyleSheet("color: #44FF44; font-size: 14px; font-weight: bold; background: transparent;")
        else:
            self.voice_sync_label.setText("🎤 V: Off")
            self.voice_sync_label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")

    def _apply_speed_suggestion(self, new_speed):
        """Aplica una velocidad sugerida por la sincronización (hilo Qt)."""
        if new_speed and new_speed != self.scroll_speed:
            self.scroll_speed = new_speed
            self._update_timer_interval()
            self.speed_label.setText(f"⚡ {new_speed}")

    def closeEvent(self, event):
        """Cerrar la aplicación y guardar configuración."""
        if self.speech_sync and self.speech_sync_active:
            self.speech_sync.stop()
        if self.remote_server is not None:
            try:
                self.remote_server.stop()
            except Exception as e:
                log.warning("Error al detener el servidor remoto: %s", e)
        self._save_current_config()
        event.accept()

    # ── Lógica de scroll ───────────────────────────────────────

    def _scroll_step(self):
        """Un paso de scroll automático."""
        if self.is_running:
            scrollbar = self.text_widget.verticalScrollBar()
            step = max(1, self.scroll_speed // 2)
            scrollbar.setValue(scrollbar.value() + step)

    def _update_timer_interval(self):
        """Actualiza el intervalo del timer según la velocidad."""
        interval = max(5, int(50 / self.scroll_speed))
        self.scroll_timer.setInterval(interval)

    def _update_progress(self):
        """Actualiza la barra de progreso y el tiempo restante."""
        scrollbar = self.text_widget.verticalScrollBar()
        max_scroll = scrollbar.maximum()

        if max_scroll > 0:
            progress = int((scrollbar.value() / max_scroll) * 100)
            self.progress_bar.setValue(progress)

            # Palabras desplazadas estimadas
            words_scrolled = int(self.total_words * (scrollbar.value() / max_scroll))
            self.words_label.setText(f"📝 {words_scrolled} / {self.total_words}")

            # Tiempo restante estimado
            if self.is_running and self.scroll_speed > 0:
                remaining_scroll = max_scroll - scrollbar.value()
                pixels_per_step = max(1, self.scroll_speed // 2)
                interval_ms = max(5, int(50 / self.scroll_speed))
                steps_remaining = remaining_scroll / pixels_per_step
                seconds_remaining = (steps_remaining * interval_ms) / 1000
                minutes = int(seconds_remaining // 60)
                seconds = int(seconds_remaining % 60)
                self.time_label.setText(f"⏱ {minutes:02d}:{seconds:02d}")
            elif max_scroll > 0:
                # Estimar duración total basada en WPM
                total_seconds = (self.total_words / self.wpm) * 60
                minutes = int(total_seconds // 60)
                seconds = int(total_seconds % 60)
                self.time_label.setText(f"⏱ ~{minutes}:{seconds:02d}")
        else:
            self.progress_bar.setValue(0)
            self.time_label.setText("⏱ --:--")

    # ── Servidor remoto ───────────────────────────────────────

    def _setup_remote_server(self):
        """
        Crea e inicia el servidor remoto bajo demanda.

        Fase 0: el servidor no se inicia automáticamente con la app;
        se activa cuando el usuario pulsa Q o pide el código QR, y
        queda vinculado a la red local únicamente mientras se usa.
        """
        if self.remote_server is not None and self.remote_server.is_running():
            return self.remote_server

        try:
            from remote_server import RemoteServer
            self.remote_server = RemoteServer(self, port=5000)
            self.remote_server.start()
            log.info("Control remoto disponible en: %s", self.remote_server.url)
            return self.remote_server
        except Exception as e:
            log.error("Error al iniciar el servidor remoto: %s", e)
            self.status_label.setText(f"❌ Control remoto: {e}")
            return None

    def show_qr_code(self):
        """Muestra el código QR para conectarse al control remoto."""
        # Arranca el servidor bajo demanda
        if not self.remote_server or not self.remote_server.is_running():
            if self._setup_remote_server() is None:
                return

        dialog = QDialog(self)
        dialog.setWindowTitle("Control Remoto")
        dialog.setMinimumSize(350, 450)
        dialog.setStyleSheet("background-color: #1a1a2e;")

        layout = DialogLayout(dialog)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Título
        title = QLabel("📱 Conecta tu teléfono")
        title.setStyleSheet("color: #FFD700; font-size: 18px; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # QR Code
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Generar QR
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(self.remote_server.url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Convertir a QPixmap
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.read())
        qr_label.setPixmap(pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio))
        layout.addWidget(qr_label)

        # URL
        url_label = QLabel(self.remote_server.url)
        url_label.setStyleSheet("color: #888; font-size: 12px; background: transparent;")
        url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(url_label)

        # Instrucciones
        instructions = QLabel("1. Conéctate a la misma red WiFi\n2. Abre la cámara del teléfono\n3. Escanea el código QR")
        instructions.setStyleSheet("color: #aaa; font-size: 14px; background: transparent; margin-top: 10px;")
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(instructions)

        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: black;
                border: none;
                border-radius: 10px;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
                margin-top: 15px;
            }
            QPushButton:hover {
                background-color: #FFC107;
            }
        """)
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.exec()

    # ── Métodos internos ───────────────────────────────────────

    def _update_font(self):
        """Aplica el tamaño de fuente actual al widget."""
        font = QFont(self.font_family, self.font_size)
        font.setBold(True)
        self.text_widget.setFont(font)

    def _apply_mirror(self):
        """
        Invierte el texto horizontalmente (modo espejo).

        Fase 0: transformación visual real. MirrorView pinta una copia
        reflejada del QTextEdit; el original se oculta para no pintar
        dos veces. Antes solo se cambiaba la dirección del layout, lo
        cual reordena elementos pero no refleja nada.
        """
        if self.is_mirror:
            if self._mirror_host is None:
                self._mirror_host = MirrorView(self.text_widget)
                self.text_layout.addWidget(self._mirror_host)
            self._mirror_host.show()
            self.text_widget.hide()
        else:
            self.text_widget.show()
            if self._mirror_host is not None:
                self._mirror_host.hide()

    def toggle_mirror(self):
        """Alterna el modo espejo (transformación visual real)."""
        self.is_mirror = not self.is_mirror
        self._apply_mirror()

    def _save_current_config(self):
        """Guarda la configuración actual para la próxima vez."""
        self.config["scroll_speed"] = self.scroll_speed
        self.config["font_size"] = self.font_size
        self.config["mirror_mode"] = self.is_mirror
        self.config["wpm"] = self.wpm
        save_config(self.config)

    # ── Eventos de teclado ─────────────────────────────────────

    def keyPressEvent(self, event):
        """Maneja los eventos de teclado."""
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Space:
            self.toggle()
        elif key == Qt.Key.Key_Up:
            if modifiers == Qt.KeyboardModifier.ShiftModifier:
                self.scroll_speed += 10
                self._update_timer_interval()
                self.speed_label.setText(f"⚡ {self.scroll_speed}")
            elif modifiers == Qt.KeyboardModifier.ControlModifier:
                self.scroll_speed += 5
                self._update_timer_interval()
                self.speed_label.setText(f"⚡ {self.scroll_speed}")
            else:
                self.speed_up()
        elif key == Qt.Key.Key_Down:
            if modifiers == Qt.KeyboardModifier.ShiftModifier:
                if self.scroll_speed > 10:
                    self.scroll_speed -= 10
                    self._update_timer_interval()
                    self.speed_label.setText(f"⚡ {self.scroll_speed}")
            elif modifiers == Qt.KeyboardModifier.ControlModifier:
                if self.scroll_speed > 5:
                    self.scroll_speed -= 5
                    self._update_timer_interval()
                    self.speed_label.setText(f"⚡ {self.scroll_speed}")
            else:
                self.speed_down()
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_R):
            self.reset()
        elif key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
            self.font_bigger()
        elif key == Qt.Key.Key_Minus:
            self.font_smaller()
        elif key == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_O:
            self.open_script()
        elif key == Qt.Key.Key_G:
            self.toggle_guide_line()
        elif key == Qt.Key.Key_M:
            self.toggle_mirror()
        elif key == Qt.Key.Key_Q:
            self.show_qr_code()
        elif key == Qt.Key.Key_V:
            self.toggle_speech_sync()
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Control de velocidad con la rueda del mouse."""
        delta = event.angleDelta().y()
        if delta > 0:
            self.speed_up()
        elif delta < 0:
            self.speed_down()

    def show(self):
        """Asegura que la ventana tenga foco al mostrarse."""
        super().show()
        self.activateWindow()
        self.raise_()
