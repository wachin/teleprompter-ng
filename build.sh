#!/bin/bash
# build.sh — Script para empaquetar Teleprompter Pro con PyInstaller
#
# Uso:
#   ./build.sh          # Empaquetar en modo directorio (rápido para pruebas)
#   ./build.sh --onefile # Empaquetar en un solo ejecutable (más lento)
#
# Requisitos:
#   pip install -r requirements.txt

set -e

echo "🎬 Teleprompter Pro — Script de empaquetado"
echo "============================================"

# Verificar que PyInstaller está instalado
if ! python3 -m PyInstaller --version &> /dev/null; then
    echo "❌ PyInstaller no está instalado. Ejecuta:"
    echo "   pip install pyinstaller"
    exit 1
fi

# Verificar que los archivos necesarios existen
if [ ! -f "main.py" ]; then
    echo "❌ No se encontró main.py"
    exit 1
fi

# Limpiar builds anteriores
echo "🧹 Limpiando builds anteriores..."
rm -rf build/ dist/ *.spec

# Determinar modo de empaquetado
if [ "$1" = "--onefile" ]; then
    echo "📦 Empaquetando en modo ONEFILE..."
    MODE="--onefile"
else
    echo "📁 Empaquetando en modo DIRECTORIO..."
    MODE="--onedir"
fi

# Ejecutar PyInstaller
echo "⚙️  Ejecutando PyInstaller..."
python3 -m PyInstaller \
    --name "TeleprompterPro" \
    --noconfirm \
    --clean \
    $MODE \
    --add-data "scripts:scripts" \
    --add-data "templates:templates" \
    --hidden-import "PyQt6.sip" \
    --hidden-import "PyQt6.QtWidgets" \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "flask" \
    --hidden-import "flask_socketio" \
    --hidden-import "socketio" \
    --hidden-import "qrcode" \
    --hidden-import "vosk" \
    --hidden-import "sounddevice" \
    --collect-all "vosk" \
    --collect-all "qrcode" \
    main.py

# Verificar resultado
if [ -d "dist/TeleprompterPro" ] || [ -f "dist/TeleprompterPro" ]; then
    echo ""
    echo "✅ ¡Empaquetado exitoso!"
    echo ""
    echo "📁 Archivo(s) generado(s) en: dist/"
    if [ -d "dist/TeleprompterPro" ]; then
        echo "   dist/TeleprompterPro/"
        echo ""
        echo "Para ejecutar:"
        echo "   ./dist/TeleprompterPro/TeleprompterPro"
    else
        echo "   dist/TeleprompterPro"
        echo ""
        echo "Para ejecutar:"
        echo "   ./dist/TeleprompterPro"
    fi
    echo ""
    echo "⚠️  Nota: El modelo de Vosk (model-es/) debe estar en la misma carpeta"
    echo "   que el ejecutable para que la sincronización de voz funcione."
else
    echo "❌ Error al empaquetar. Revisa los logs arriba."
    exit 1
fi
