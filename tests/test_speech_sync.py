"""
tests/test_speech_sync.py — Tests unitarios para speech_sync.py

Fase 0: _adjust_speed ya no modifica el teleprompter directamente
(aquello actualizaba widgets Qt desde el hilo de audio). Ahora
devuelve la velocidad sugerida y la UI la aplica en su hilo.
"""

from unittest.mock import MagicMock, patch


def _make_mock_teleprompter():
    """Crea un teleprompter mock para testing."""
    tp = MagicMock()
    tp.config = {"wpm": 150}
    tp.scroll_speed = 3
    tp.speed_label = MagicMock()
    return tp


class TestSpeechSync:
    """Tests para la clase SpeechSync."""

    def _make_mock_teleprompter(self):
        """Crea un teleprompter mock para testing."""
        return _make_mock_teleprompter()

    def test_set_script_normalizes_text(self):
        """set_script normaliza el texto correctamente."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.set_script("Hola, ¿cómo estás? ¡Muy bien!")
            assert "hola" in sync.script_words
            assert "cómo" in sync.script_words
            assert "estás" in sync.script_words

    def test_get_sync_status_inactive(self):
        """get_sync_status retorna estado inactivo."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            status = sync.get_sync_status()
            assert status["active"] is False
            assert status["current_wpm"] == 0

    def test_adjust_speed_returns_suggestion_when_fast(self):
        """Devuelve velocidad mayor cuando el orador habla rápido."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        tp.scroll_speed = 5
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            suggestion = sync._adjust_speed(200)  # 200 > 150 * 1.1
            assert suggestion == 6
            # Fase 0: no debe tocar el teleprompter desde este hilo
            assert tp.scroll_speed == 5

    def test_adjust_speed_returns_suggestion_when_slow(self):
        """Devuelve velocidad menor cuando el orador habla lento."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        tp.scroll_speed = 5
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            suggestion = sync._adjust_speed(100)  # 100 < 150 * 0.9
            assert suggestion == 4
            assert tp.scroll_speed == 5

    def test_adjust_speed_stays_same_when_on_target(self):
        """No cambia velocidad cuando el orador va bien."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        tp.scroll_speed = 5
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            suggestion = sync._adjust_speed(150)  # 150 == target
            assert suggestion == 5

    def test_adjust_speed_minimum_limit(self):
        """La velocidad sugerida no baja de 1."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        tp.scroll_speed = 2
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            suggestion = sync._adjust_speed(50)  # Muy lento
            assert suggestion >= 1

    def test_adjust_speed_maximum_limit(self):
        """La velocidad sugerida no sube de 50."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        tp.scroll_speed = 49
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            suggestion = sync._adjust_speed(300)  # Muy rápido
            assert suggestion <= 50

    def test_adjust_speed_ignores_invalid_input(self):
        """WPM inválido o target inválido devuelven None sin error."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            assert sync._adjust_speed(0) is None
            assert sync._adjust_speed(-10) is None
            sync.target_wpm = 0
            assert sync._adjust_speed(150) is None


class TestSpeechSyncStreamLifecycle:
    """Tests del ciclo de vida del stream de audio (bug Fase 0)."""

    def test_start_keeps_stream_open(self):
        """start() debe dejar el stream vivo en self._stream."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)

        # Simular modelo disponible
        sync.model = MagicMock()
        sync.recognizer = MagicMock()

        with patch("speech_sync.sd.RawInputStream") as mock_stream_cls:
            stream = MagicMock()
            mock_stream_cls.return_value = stream

            assert sync.start() is True
            # El stream debe seguir abierto tras retornar de start()
            assert sync._stream is stream
            stream.start.assert_called_once()

            sync.stop()
            stream.stop.assert_called_once()
            stream.close.assert_called_once()
            assert sync._stream is None

    def test_stop_is_idempotent(self):
        """stop() dos veces no lanza error."""
        from speech_sync import SpeechSync

        tp = _make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
        sync.model = MagicMock()
        sync.recognizer = MagicMock()

        with patch("speech_sync.sd.RawInputStream"):
            sync.start()
            sync.stop()
            sync.stop()  # No debe lanzar excepción

    def test_normalize_words_keeps_accents(self):
        """La normalización conserva acentos y ñ."""
        from speech_sync import normalize_words

        words = normalize_words("¡Ñandú comía allí!")
        assert words == ["ñandú", "comía", "allí"]
