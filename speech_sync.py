"""
speech_sync.py — Sincronización inteligente del teleprompter con la voz.

Usa Vosk para reconocimiento de voz local y compara lo que se dice
contra el guion para ajustar automáticamente la velocidad de scroll.
"""

import json
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
    print("[SpeechSync] Vosk no instalado. Ejecuta: pip install vosk sounddevice")


class SpeechSync:
    def __init__(self, teleprompter, model_path="model-es"):
        """
        Inicializa el sincronizador de voz.

        Args:
            teleprompter: Instancia de la clase Teleprompter
            model_path: Ruta al modelo de Vosk (descargado previamente)
        """
        self.teleprompter = teleprompter
        self.model_path = model_path
        self.is_active = False
        self.model = None
        self.recognizer = None

        # Texto del guion para comparar
        self.script_text = ""
        self.script_words = []
        self.current_position = 0  # Posición en el guion

        # Estadísticas
        self.wpm_history = deque(maxlen=10)  # Historial de WPM
        self.target_wpm = teleprompter.config.get("wpm", 150)
        self.last_words_spoken = 0
        self.last_time = time.time()

        # Cola de audio
        self.audio_queue = queue.Queue()

        # Callbacks
        self.on_status_change = None  # Callback para cambios de estado
        self.on_wpm_update = None     # Callback para actualización de WPM

        # Inicializar modelo si está disponible
        if VOSK_AVAILABLE:
            self._init_model()

    def _init_model(self):
        """Inicializa el modelo de reconocimiento de voz."""
        try:
            # Usar modelo pequeño en español si existe
            if os.path.exists(self.model_path):
                self.model = vosk.Model(self.model_path)
                self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
                print(f"[SpeechSync] Modelo cargado: {self.model_path}")
            else:
                print(f"[SpeechSync] Modelo no encontrado en {self.model_path}")
                print("[SpeechSync] Descarga el modelo de: https://alphacephei.com/vosk/models")
                print("[SpeechSync] Usa: model-es para español")
        except Exception as e:
            print(f"[SpeechSync] Error al cargar modelo: {e}")

    def set_script(self, text):
        """Establece el texto del guion para comparar."""
        self.script_text = text
        # Limpiar y normalizar el texto
        text_clean = re.sub(r'[^\w\s]', '', text.lower())
        self.script_words = text_clean.split()
        self.current_position = 0

    def start(self):
        """Inicia la sincronización de voz."""
        if not VOSK_AVAILABLE or not self.model:
            print("[SpeechSync] No disponible - Vosk no instalado o modelo no cargado")
            return False

        try:
            # Iniciar captura de audio
            with sd.RawInputStream(
                samplerate=16000,
                blocksize=8000,
                dtype='int16',
                channels=1,
                callback=self._audio_callback
            ):
                self.is_active = True
                self.last_time = time.time()
                self.last_words_spoken = 0

                # Hilo para procesar audio
                self.process_thread = threading.Thread(
                    target=self._process_audio,
                    daemon=True
                )
                self.process_thread.start()

                print("[SpeechSync] Sincronización de voz activada")
                if self.on_status_change:
                    self.on_status_change("active")
                return True

        except Exception as e:
            print(f"[SpeechSync] Error al iniciar: {e}")
            print("[SpeechSync] Verifica que el micrófono esté disponible")
            return False

    def stop(self):
        """Detiene la sincronización de voz."""
        self.is_active = False
        print("[SpeechSync] Sincronización de voz desactivada")
        if self.on_status_change:
            self.on_status_change("inactive")

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback para capturar audio del micrófono."""
        if status:
            print(f"[SpeechSync] Audio status: {status}")
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
                print(f"[SpeechSync] Error procesando audio: {e}")

    def _process_recognized_text(self, text, partial=False):
        """Procesa el texto reconocido y ajusta la velocidad."""
        if not text.strip():
            return

        # Calcular WPM actual
        current_time = time.time()
        time_elapsed = current_time - self.last_time

        if time_elapsed >= 5:  # Calcular cada 5 segundos
            words = len(text.split())
            wpm = int((words / time_elapsed) * 60)
            self.wpm_history.append(wpm)

            # Calcular WPM promedio
            avg_wpm = sum(self.wpm_history) / len(self.wpm_history)

            # Comparar con WPM objetivo
            self._adjust_speed(avg_wpm)

            # Actualizar estadísticas
            self.last_words_spoken = words
            self.last_time = current_time

            if self.on_wpm_update:
                self.on_wpm_update(avg_wpm, self.target_wpm)

    def _adjust_speed(self, current_wpm):
        """Ajusta la velocidad del scroll según el WPM actual."""
        if current_wpm <= 0 or self.target_wpm <= 0:
            return

        # Calcular factor de ajuste
        ratio = current_wpm / self.target_wpm

        # Obtener velocidad actual
        current_speed = self.teleprompter.scroll_speed

        # Ajustar suavemente
        if ratio > 1.1:  # Hablando muy rápido
            # Aumentar velocidad del scroll
            new_speed = min(current_speed + 1, 50)
        elif ratio < 0.9:  # Hablando muy lento
            # Disminuir velocidad del scroll
            new_speed = max(current_speed - 1, 1)
        else:
            new_speed = current_speed

        # Aplicar nuevo velocidad si cambió
        if new_speed != current_speed:
            self.teleprompter.scroll_speed = new_speed
            self.teleprompter._update_timer_interval()
            self.teleprompter.speed_label.setText(f"⚡ {new_speed}")
            print(f"[SpeechSync] Velocidad ajustada: {current_speed} → {new_speed} (WPM: {current_wpm:.0f})")

    def get_sync_status(self):
        """Retorna el estado actual de sincronización."""
        if not self.wpm_history:
            return {
                "active": self.is_active,
                "current_wpm": 0,
                "target_wpm": self.target_wpm,
                "ratio": 0,
                "status": "waiting"
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
            "status": status
        }


# Importar os al inicio del archivo
import os
