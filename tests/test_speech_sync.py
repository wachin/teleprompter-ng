"""
tests/test_speech_sync.py — Tests unitarios para speech_sync.py
"""

import pytest
from unittest.mock import MagicMock, patch


class TestSpeechSync:
    """Tests para la clase SpeechSync."""

    def _make_mock_teleprompter(self):
        """Crea un teleprompter mock para testing."""
        tp = MagicMock()
        tp.config = {"wpm": 150}
        tp.scroll_speed = 3
        tp.speed_label = MagicMock()
        return tp

    def test_set_script_normalizes_text(self):
        """set_script normaliza el texto correctamente."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.set_script("Hola, ¿cómo estás? ¡Muy bien!")
            assert "hola" in sync.script_words
            assert "cómo" in sync.script_words
            assert "estás" in sync.script_words

    def test_get_sync_status_inactive(self):
        """get_sync_status retorna estado inactivo."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            status = sync.get_sync_status()
            assert status["active"] is False
            assert status["current_wpm"] == 0

    def test_adjust_speed_increases_when_fast(self):
        """Aumenta velocidad cuando el orador habla rápido."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        tp.scroll_speed = 5
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            sync._adjust_speed(200)  # 200 > 150 * 1.1
            assert tp.scroll_speed == 6

    def test_adjust_speed_decreases_when_slow(self):
        """Disminuye velocidad cuando el orador habla lento."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        tp.scroll_speed = 5
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            sync._adjust_speed(100)  # 100 < 150 * 0.9
            assert tp.scroll_speed == 4

    def test_adjust_speed_stays_same_when_on_target(self):
        """No cambia velocidad cuando el orador va bien."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        tp.scroll_speed = 5
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            sync._adjust_speed(150)  # 150 == target
            assert tp.scroll_speed == 5

    def test_adjust_speed_minimum_limit(self):
        """La velocidad no baja de 1."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        tp.scroll_speed = 2
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            sync._adjust_speed(50)  # Muy lento
            assert tp.scroll_speed >= 1

    def test_adjust_speed_maximum_limit(self):
        """La velocidad no sube de 50."""
        from speech_sync import SpeechSync

        tp = self._make_mock_teleprompter()
        tp.scroll_speed = 49
        with patch.object(SpeechSync, '_init_model'):
            sync = SpeechSync(tp)
            sync.target_wpm = 150
            sync._adjust_speed(300)  # Muy rápido
            assert tp.scroll_speed <= 50
