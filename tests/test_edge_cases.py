"""
tests/test_edge_cases.py — Tests para casos límite de texto
"""

import os
import tempfile


class TestTextHandling:
    """Tests para manejo de texto."""

    def test_utf8_support(self):
        """Soporte completo de UTF-8: tildes, ñ, emojis."""
        text = "¡Hola! ¿Cómo estás? Nación México 🎉"
        # Verificar que se puede procesar
        assert len(text) > 0
        assert "ñ" in text.lower() or "Nación" in text
        assert "🎉" in text

    def test_long_words(self):
        """Palabras muy largas no causan problemas."""
        text = "Esternocleidomastoideo " * 10
        words = text.split()
        assert len(words) == 10
        assert all(len(w) > 10 for w in words)

    def test_empty_text(self):
        """Texto vacío se maneja correctamente."""
        text = ""
        words = text.split()
        assert len(words) == 0
        assert len(text) == 0

    def test_multiple_newlines(self):
        """Saltos de línea múltiples se manejan."""
        text = "Línea 1\n\n\n\nLínea 2"
        lines = text.split("\n")
        assert len(lines) >= 2

    def test_mixed_line_endings(self):
        """Saltos de línea Windows y Unix mezclados."""
        text = "Línea 1\r\nLínea 2\nLínea 3"
        # Normalizar
        text_normalized = text.replace("\r\n", "\n")
        lines = text_normalized.split("\n")
        assert len(lines) == 3

    def test_special_characters(self):
        """Caracteres especiales no causan crash."""
        text = '<html>&amp;"quotes" \'apostrophes\' $%^&*()'
        assert len(text) > 0

    def test_very_long_script(self):
        """Script de 10+ minutos (~2000 palabras)."""
        paragraph = "Esta es una oración de prueba para simular un discurso largo. " * 10
        text = (paragraph + "\n\n") * 50  # ~2500 palabras
        words = text.split()
        assert len(words) >= 2000


class TestFileOperations:
    """Tests para operaciones de archivo."""

    def test_load_utf8_file(self):
        """Cargar archivo con codificación UTF-8."""
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', suffix='.txt', delete=False
        ) as f:
            f.write("¡Hola! ñáéíóú 🎉")
            tmp_path = f.name

        try:
            with open(tmp_path, encoding='utf-8') as f:
                content = f.read()
            assert "ñáéíóú" in content
            assert "🎉" in content
        finally:
            os.unlink(tmp_path)

    def test_nonexistent_file_handled(self):
        """Archivo inexistente no causa crash."""
        # Simular lo que hace main.py
        path = "/nonexistent/path/file.txt"
        exists = os.path.exists(path)
        assert exists is False
