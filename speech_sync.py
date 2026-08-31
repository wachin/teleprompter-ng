"""
speech_sync.py — Sincronización inteligente del teleprompter con la voz.

Usa Vosk para reconocimiento de voz local y compara lo que se dice
contra el guion para ajustar automáticamente la velocidad de scroll.

Fase 0: el stream de audio ahora permanece abierto mientras la
sincronización está activa (antes se cerraba al instante por un
`with` que salía de alcance). Las actualizaciones hacia la interfaz
se canalizan mediante callbacks que la UI conecta a señales Qt, nunca
tocando widgets directamente desde el hilo de audio.
"""

import json
import os
import queue
import re
import threading
import time
from collections import deque

try:
    import vosk
    import sounddevice as sd
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

from logging_setup import get_logger

log = get_logger("SpeechSync")

# Directorio de modelos: raíz de la aplicación / models
_MODEL_DIRS = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"),
    os.path.dirname(os.path.abspath(__file__)),  # compatibilidad: junto a ui.py
)


def _find_model(candidate_names):
    """Busca un modelo de Vosk en los directorios conocidos."""
    for base in _MODEL_DIRS:
        for name in candidate_names:
            path = os.path.join(base, name)
            if os.path.isdir(path) and os.path.isfile(os.path.join(path, "conf")):
                return path
    return None


def normalize_words(text):
    """Normaliza texto a palabras minúsculas sin puntuación."""
    clean = re.sub(r"[^\w\sáéíóúñüÁÉÍÓÚÑÜ]", "", text.lower(), flags=re.UNICODE)
    return clean.split()


class SpeechSync:
    def __init__(self, teleprompter, model_path=None):
        """
        Inicializa el sincronizador de voz.

        Args:
            teleprompter: Instancia de la clase Teleprompter
            model_path: Ruta opcional al modelo de Vosk. Si es None,
                        se buscan modelos habituales en models/.
        """
        self.teleprompter = teleprompter
        self.is_active = False
        self.model = None
        self.recognizer = None

        # Texto del guion para comparar
        self.script_text = ""
        self.script_words = []
        self.current_position = 0  # Posición en el guion

        # Estadísticas
        self.wpm_history = deque(maxlen=10)
        self.target_wpm = teleprompter.config.get("wpm", 150)
        self.last_words_spoken = 0
        self.last_time = time.time()

        # Cola de audio y control de hilos
        self.audio_queue = queue.Queue()
        self._stream = None
        self._process_thread = None

        # Callbacks hacia la interfaz (la UI decide cómo aplicarlos)
        self.on_status_change = None  # Callback para cambios de estado
        self.on_wpm_update = None     # Callback para actualización de WPM

        if VOSK_AVAILABLE:
            self._init_model(model_path)
        else:
            log.info("Vosk not installed. Install vosk and sounddevice to use this feature")

    def _init_model(self, model_path=None):
        """Inicializa el modelo de reconocimiento de voz."""
        try:
            if model_path is None:
                model_path = _find_model(("model-es", "vosk-model-es-0.42", "model"))

            if model_path and os.path.isdir(model_path):
                self.model = vosk.Model(model_path)
                self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
                log.info("Modelo de voz cargado: %s", model_path)
            else:
                log.warning(
                    "Voice model not found. Download it from "
                    "https://alphacephei.com/vosk/models and place it in models/model-es"
                )
        except Exception as e:
            log.error("Error al cargar el modelo de voz: %s", e)

    def set_script(self, text):
        """Establece el texto del guion para comparar."""
        self.script_text = text
        self.script_words = normalize_words(text)
        self.current_position = 0

    def start(self):
        """Inicia la sincronización de voz."""
        if not VOSK_AVAILABLE or not self.model:
            log.warning("No disponible: Vosk no instalado o modelo no cargado")
            return False

        if self.is_active:
            log.info("Voice sync is already active")
            return True

        try:
            self.audio_queue = queue.Queue()
            # El stream se guarda en self._stream y permanece abierto
            # hasta que stop() lo cierra explícitamente.
            self._stream = sd.RawInputStream(
                samplerate=16000,
                blocksize=8000,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            )
            self._stream.start()

            self.is_active = True
            self.last_time = time.time()
            self.last_words_spoken = 0

            self._process_thread = threading.Thread(
                target=self._process_audio,
                daemon=True,
                name="speech-sync",
            )
            self._process_thread.start()

            log.info("Voice synchronization activated")
            if self.on_status_change:
                self.on_status_change("active")
            return True

        except Exception as e:
            log.error("Error al iniciar la captura de audio: %s", e)
            log.error("Check that the microphone is available and connected")
            self._release_stream()
            return False

    def stop(self):
        """Detiene la sincronización de voz y libera el micrófono."""
        self.is_active = False
        self._release_stream()
        if self._process_thread is not None:
            self._process_thread.join(timeout=2)
            self._process_thread = None
        log.info("Voice synchronization deactivated")
        if self.on_status_change:
            self.on_status_change("inactive")

    def _release_stream(self):
        """Cierra el stream de audio de forma segura."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.warning("Error closing the audio stream: %s", e)
            finally:
                self._stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback para capturar audio del micrófono."""
        if status:
            log.warning("Audio status: %s", status)
        self.audio_queue.put(bytes(indata))

    def _process_audio(self):
        """Procesa el audio capturado y reconoce voz."""
        while self.is_active:
            try:
                data = self.audio_queue.get(timeout=0.1)
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "")
                    if text:
                        self._process_recognized_text(text)
                else:
                    partial = json.loads(self.recognizer.PartialResult())
                    partial_text = partial.get("partial", "")
                    if partial_text:
                        self._process_recognized_text(partial_text, partial=True)
            except queue.Empty:
                continue
            except Exception as e:
                if self.is_active:
                    log.error("Error processing audio: %s", e)

    def _process_recognized_text(self, text, partial=False):
        """Procesa el texto reconocido y ajusta la velocidad."""
        if not text.strip():
            return

        current_time = time.time()
        time_elapsed = current_time - self.last_time

        if time_elapsed >= 5:  # Calcular cada 5 segundos
            words = len(text.split())
            wpm = int((words / time_elapsed) * 60)
            self.wpm_history.append(wpm)

            avg_wpm = sum(self.wpm_history) / len(self.wpm_history)

            self._adjust_speed(avg_wpm)

            self.last_words_spoken = words
            self.last_time = current_time

            if self.on_wpm_update:
                self.on_wpm_update(avg_wpm, self.target_wpm)

    def _adjust_speed(self, current_wpm):
        """
        Calcula la nueva velocidad y delega la aplicación en la UI.

        La UI debe aplicar el cambio (y actualizar sus etiquetas) desde
        el hilo principal de Qt; este método solo calcula.
        """
        if current_wpm <= 0 or self.target_wpm <= 0:
            return None

        ratio = current_wpm / self.target_wpm
        current_speed = self.teleprompter.scroll_speed

        if ratio > 1.1:  # Hablando muy rápido
            new_speed = min(current_speed + 1, 50)
        elif ratio < 0.9:  # Hablando muy lento
            new_speed = max(current_speed - 1, 1)
        else:
            new_speed = current_speed

        if new_speed != current_speed:
            log.info(
                "Velocidad sugerida: %s → %s (WPM: %.0f)",
                current_speed, new_speed, current_wpm,
            )

        return new_speed

    def get_sync_status(self):
        """Retorna el estado actual de sincronización."""
        if not self.wpm_history:
            return {
                "active": self.is_active,
                "current_wpm": 0,
                "target_wpm": self.target_wpm,
                "ratio": 0,
                "status": "waiting",
            }

        avg_wpm = sum(self.wpm_history) / len(self.wpm_history)
        ratio = avg_wpm / self.target_wpm if self.target_wpm > 0 else 0

        if ratio > 1.1:
            status = "fast"  # Va rápido - mostrar rojo
        elif ratio < 0.9:
            status = "slow"  # Va lento - mostrar amarillo
        else:
            status = "good"  # Va bien - mostrar verde

        return {
            "active": self.is_active,
            "current_wpm": avg_wpm,
            "target_wpm": self.target_wpm,
            "ratio": ratio,
            "status": status,
        }
