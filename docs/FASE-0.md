# Fase 0 — Auditoría y seguridad del código

Estado: **completada** el 2026-08-30.

## Resumen de la auditoría

| Archivo | Responsabilidad | Problema encontrado → corregido |
|---|---|---|
| `main.py` | Entrada | Guion dependía del directorio de trabajo → resuelto con `paths.py` |
| `ui.py` | UI PyQt6 (616→745 líneas) | Espejo falso, servidor remoto siempre activo, UI tocada desde hilos |
| `speech_sync.py` | Sincronización de voz (Vosk) | `RawInputStream` se cerraba al instante; UI tocada desde hilo de audio |
| `remote_server.py` | Control remoto (Flask + Socket.IO) | `SECRET_KEY` fija, plantilla con ruta relativa, sin apagado real |
| `config.py` | Configuración persistente (XDG) | Sin validar tipos del JSON guardado |
| `tests/` | Pruebas unitarias | 27 → 41 pruebas, cubren todos los errores corregidos |

## Correcciones aplicadas

### 1. Stream de audio (bug crítico en `speech_sync.py`)

`start()` usaba `with sd.RawInputStream(...)`; el gestor de contexto cerraba
el micrófono apenas retornaba la función, antes de que el hilo de
procesamiento pudiera capturar nada. Ahora el stream se guarda en
`self._stream` y permanece abierto hasta que `stop()` lo cierra
explícitamente (con `join()` del hilo de procesamiento).

### 2. Hilos y widgets Qt

`_adjust_speed` actualizaba directamente `speed_label.setText()` desde el
hilo de audio — algo prohibido en Qt. Ahora la clase `SpeechSync` solo
calcula y devuelve la velocidad sugerida; la UI la aplica en el hilo
principal mediante la señal `pyqtSignal(int)` `_SpeechSignals.speed_suggestion`.

### 3. Modo espejo con transformación visual real

El modo espejo usaba `setLayoutDirection(RightToLeft)`, que solo reordena
elementos del layout sin reflejarlos — inútil para un teleprompter de
cristal. Ahora `MirrorView` pinta una copia reflejada del `QTextEdit`
(`grab()` + `QPainter` con `scale(-1, 1)`), se repinta con cada cambio del
scroll y el original se oculta. Nuevo atajo de teclado **M**.

### 4. Servidor remoto seguro

- `SECRET_KEY` estática eliminada → `secrets.token_hex(32)` por ejecución.
- Plantilla resuelta con `paths.templates_dir()` (funciona desde cualquier
  directorio y en PyInstaller).
- **No arranca automáticamente**: se activa bajo demanda con **Q**.
- `stop()` real mediante `werkzeug.make_server().shutdown()` — antes el
  puerto 5000 quedaba ocupado hasta matar el proceso.
- `closeEvent` de la ventana detiene servidor y sincronización de voz.

### 5. Rutas independientes del directorio de trabajo

Nuevo módulo `paths.py`:
- `get_app_dir()` detecta PyInstaller (`sys.frozen`) o repositorio.
- `resolve_script_path()` encuentra `scripts/guion_actual.txt` desde
  cualquier cwd.
- `templates_dir()`, `models_dir()`, `relative_to()`.

### 6. Registro estructurado

Nuevo módulo `logging_setup.py`: niveles DEBUG/INFO/WARNING/ERROR, salida
a consola y al journal de systemd (`/dev/log`) si existe. Todas las
impresiones `print()` de diagnóstico fueron reemplazadas por logging.

### 7. Configuración con validación de tipos

`load_config()` ahora verifica que cada clave guardada tenga el tipo
correcto (`int`, `bool`, `str`); si no, usa el valor por defecto. Un
`config.json` manipulado ya no rompe la interfaz.

## Pruebas

- Unitarias: **41/41 pasan** (`python3 -m pytest tests/`)
  - Nuevas: 9 de `paths.py`, 3 del ciclo de vida del stream, 1 de
    normalización con acentos, 1 de tipos inválidos en config.
- Smoke test Qt desde `/tmp`: ventana creada, espejo real aplicado,
  capturado y liberado, cierre limpio.
- Integración HTTP: `/`, `/qr`, `/api/status` responden; `stop()` libera
  el puerto.
- Integración Socket.IO: `get_status`, `toggle`, `speed_up`, `reset`
  funcionan con el servidor WSGI.

## Cómo ejecutar

```bash
cd teleprompter-ng
python3 main.py                # guion por defecto
python3 main.py mi_guion.txt    # guion específico
python3 -m pytest tests/        # suite completa
```

## Siguiente fase

Fase 1 — Base PyQt6 y gestión de proyectos (MainWindow con navegación,
ProjectService, formato de proyecto versionado y plantillas de guion).
