# ROADMAP.md — Teleprompter para Linux con cámara y flujo de creación de vídeo

> Documento para un Agente de IA de programación.
>
> Objetivo: transformar el proyecto existente `teleprompter`/`Teleprompter Pro` en una aplicación Linux de escritorio, escrita en **Python + PyQt6**, que combine teleprompter, cámara web, grabación, edición básica, subtítulos y publicación/exportación

## 1. Contexto del proyecto existente

El código actual ya contiene:

- Interfaz PyQt6 en `ui.py`.
- Entrada en `main.py`.
- Configuración persistente en `config.py`.
- Carga de guiones UTF-8 desde archivos `.txt`.
- Desplazamiento automático con velocidad ajustable.
- Cuenta regresiva 3-2-1.
- Barra de progreso, tiempo estimado y contador de palabras.
- Línea guía y modo espejo.
- Control remoto local mediante Flask, Socket.IO y código QR.
- Sincronización experimental por voz usando Vosk y `sounddevice`.
- Empaquetado preliminar con PyInstaller.
- Pruebas unitarias existentes.

Antes de añadir funciones, el agente debe estudiar el código real del repositorio, corregir errores y conservar la compatibilidad de las funciones que ya funcionan.

## 2. Resultado deseado

El usuario debe poder realizar este flujo completo:

1. Crear un proyecto.
2. Escribir, pegar, importar o generar un guion.
3. Elegir una cámara web integrada o USB.
4. Verse en directo dentro de la ventana.
5. Leer el guion superpuesto sobre la imagen de la cámara, cerca de la lente.
6. Ajustar tamaño, color, posición, opacidad, velocidad y espejo del texto.
7. Grabar vídeo y audio en un archivo local.
8. Revisar la grabación.
9. Cortar silencios y fragmentos no deseados.
10. Generar subtítulos automáticamente.
11. Añadir logo, colores, introducción, cierre, música y recursos visuales.
12. Exportar en formatos habituales para YouTube, Instagram, TikTok y LinkedIn.
13. Guardar el proyecto para continuar editándolo.
14. Controlar la grabación y el teleprompter con teclado, ratón, botones grandes y teléfono.

## 3. Principios técnicos obligatorios

### 3.1 Plataforma

- Primera plataforma: Debian 13 y derivados compatibles.
- Arquitectura inicial: x86_64; no bloquear ARM64 innecesariamente.
- Soportar X11 y Wayland siempre que las bibliotecas lo permitan.
- No depender de servicios web para las funciones básicas.
- La grabación, el teleprompter, la vista previa y el guardado local deben funcionar sin Internet.

### 3.2 Interfaz

- Usar exclusivamente **PyQt6** para la interfaz nativa.
- Usar señales y slots para comunicar hilos y widgets.
- No bloquear el hilo principal de Qt.
- Mantener una interfaz clara, traducible y accesible.
- Añadir modo oscuro y controles con buen contraste.
- Usar `QSettings` o una configuración compatible con XDG; mantener migración desde el `config.json` actual.

### 3.3 Arquitectura

Separar el programa en módulos con responsabilidades claras:

```text
teleprompter/
├── app/
│   ├── main.py
│   ├── main_window.py
│   ├── models/
│   ├── services/
│   │   ├── camera_service.py
│   │   ├── audio_service.py
│   │   ├── recording_service.py
│   │   ├── subtitle_service.py
│   │   ├── export_service.py
│   │   └── project_service.py
│   ├── widgets/
│   │   ├── camera_preview.py
│   │   ├── teleprompter_overlay.py
│   │   ├── recording_controls.py
│   │   ├── script_editor.py
│   │   └── editor_timeline.py
│   ├── dialogs/
│   └── resources/
├── scripts/
├── templates/
├── tests/
├── docs/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
└── ROADMAP.md
```

El agente puede conservar nombres actuales durante una migración gradual, pero debe evitar que toda la lógica permanezca en `ui.py`.

## 4. Dependencias permitidas en Debian 13

### 4.1 Preferencia por paquetes Debian

Usar primero bibliotecas disponibles en los repositorios Debian 13 y documentar sus nombres `apt` cuando corresponda. No compilar manualmente componentes multimedia si existe una solución mantenida por Debian.

Paquetes de sistema candidatos:

```text
python3
python3-pyqt6
python3-opencv
python3-numpy
python3-pil
python3-flask
python3-flask-socketio
python3-qrcode
python3-pytest
python3-venv
ffmpeg
v4l-utils
pulseaudio-utils o pipewire-pulse
portaudio19-dev
libportaudio2
```

El agente debe verificar los nombres exactos disponibles en Debian 13 antes de fijarlos como requisito. No asumir que todos los módulos Python tienen exactamente el mismo nombre en `apt` y en PyPI.

### 4.2 Paquetes pip aceptables

Usar `pip` dentro de un entorno virtual, nunca modificar de forma irresponsable el Python del sistema. Evaluar:

- `PyQt6` si la versión de Debian no basta.
- `opencv-python` únicamente si `python3-opencv` no ofrece lo necesario.
- `sounddevice` o `soundcard` para audio.
- `vosk` para reconocimiento local existente.
- `faster-whisper` como backend opcional de subtítulos, si el rendimiento y el tamaño son aceptables.
- `qrcode` para control remoto.
- `pytest`, `pytest-qt`, `ruff`, `mypy` y herramientas de desarrollo.
- `pyinstaller` solo como opción de distribución, no como sustituto del empaquetado Debian.

Cada dependencia debe tener una justificación, licencia compatible y alternativa opcional cuando sea posible.

### 4.3 Multimedia

Preferir **FFmpeg** ejecutado como proceso externo para muxing, conversión, extracción de audio, escalado y exportación. No implementar manualmente códecs.

Usar OpenCV o Qt Multimedia para captura de cámara según pruebas reales en Debian 13. La solución debe:

- Detectar cámaras V4L2.
- Mostrar `/dev/video*` disponibles.
- Elegir resolución y FPS compatibles.
- Informar claramente si una cámara está ocupada o no tiene permisos.
- Evitar afirmar que una cámara USB funciona sin comprobar sus capacidades.

## 5. Modelo funcional de la aplicación

### 5.1 Pantallas principales

Implementar estas vistas:

1. **Inicio/Proyectos**: crear, abrir, duplicar, renombrar y eliminar proyectos.
2. **Guion**: editor de texto con contador de palabras, duración estimada, búsqueda, importación y guardado.
3. **Cámara**: vista previa con teleprompter superpuesto.
4. **Grabación**: controles, cuenta regresiva, indicadores de cámara/micrófono y estado.
5. **Revisión**: reproducir, volver a grabar o pasar al editor.
6. **Editor**: recorte, subtítulos, branding, audio y exportación.
7. **Configuración**: cámara, micrófono, idioma, accesos directos, privacidad y almacenamiento.

### 5.2 Proyecto persistente

Crear un formato de proyecto versionado, por ejemplo:

```text
MiProyecto.bigprompt/
├── project.json
├── scripts/
│   └── guion.txt
├── media/
│   ├── raw/
│   ├── exports/
│   └── assets/
├── subtitles/
└── thumbnails/
```

`project.json` debe guardar, como mínimo:

- Versión del esquema.
- Nombre y fecha de creación.
- Ruta relativa del guion.
- Configuración del teleprompter.
- Cámara y micrófono elegidos.
- Resolución y FPS.
- Clips grabados.
- Segmentos cortados.
- Estilo de subtítulos.
- Branding.
- Música y niveles de audio.
- Historial de exportaciones.

Nunca guardar rutas absolutas cuando una ruta relativa sea suficiente.

## 6. Fases de implementación

## Fase 0 — Auditoría y seguridad del código

### Objetivo
Establecer una base fiable antes de ampliar funciones.

### Tareas

- Leer todos los archivos existentes, no sobrescribir funciones útiles sin analizarlas.
- Ejecutar las pruebas actuales y registrar el estado inicial.
- Corregir errores evidentes, especialmente:
  - Gestión de hilos y recursos de audio.
  - Detención real de `RawInputStream`.
  - Actualización de widgets PyQt6 desde hilos secundarios.
  - Compatibilidad de rutas al empaquetar.
  - Carga de plantillas y modelos desde rutas instaladas.
  - Implementación real del modo espejo; no confundir dirección de layout con transformación visual.
  - Selección de guion que dependa del directorio de trabajo.
- Eliminar secretos fijos como `SECRET_KEY` estática si no son necesarios.
- Añadir registro estructurado con niveles DEBUG, INFO, WARNING y ERROR.
- Añadir comprobaciones de permisos para cámara, micrófono y directorios.

### Criterios de aceptación

- Las pruebas existentes pasan.
- La aplicación inicia desde el repositorio y desde otra carpeta.
- La aplicación no se congela al activar/desactivar voz o cerrar una grabación.
- Los fallos de dispositivos se explican en español y ofrecen una acción correctiva.

## Fase 1 — Base PyQt6 y gestión de proyectos

### Tareas

- Crear `MainWindow` con navegación entre Inicio, Guion, Cámara, Revisión y Editor.
- Implementar `ProjectService`.
- Añadir nuevo/abrir/guardar/cerrar proyecto.
- Migrar configuración actual al nuevo modelo.
- Mantener importación de `.txt` y UTF-8.
- Añadir importación opcional de `.md`, `.html` y `.docx` solo si se dispone de una dependencia fiable; el texto debe limpiarse sin introducir formato peligroso.
- Añadir plantillas de guion: tutorial, presentación, clase, noticia, reseña y anuncio.
- Calcular duración aproximada usando WPM y mostrarla junto al contador.

### Criterios de aceptación

- Un proyecto se abre en otra sesión con todos sus ajustes.
- Un guion con ñ, acentos, emojis y saltos de línea se conserva correctamente.
- Los archivos temporales se separan de los archivos finales.

## Fase 2 — Cámara web en directo

### Objetivo
Mostrar la imagen de la cámara integrada o USB y superponer el guion.

### Tareas

- Detectar cámaras mediante V4L2 y/o OpenCV.
- Mostrar nombre, dispositivo, resolución y FPS.
- Permitir elegir cámara integrada o USB.
- Implementar `CameraService` en un hilo seguro.
- Mostrar la imagen en un widget PyQt6 con conversión correcta BGR/RGB y escalado respetando proporción.
- Permitir seleccionar resolución y FPS entre los modos realmente ofrecidos por la cámara.
- Añadir controles de brillo, contraste y espejo de la previsualización cuando sean compatibles.
- Mostrar mensajes para:
  - Cámara no encontrada.
  - Permiso denegado.
  - Cámara utilizada por otra aplicación.
  - Formato no compatible.
- Liberar la cámara al cambiar de dispositivo, cerrar la ventana o iniciar otra aplicación.

### Criterios de aceptación

- Funciona con la cámara integrada y con una cámara USB V4L2 probada.
- El selector no muestra como disponibles resoluciones que el dispositivo no soporta.
- La vista permanece fluida sin bloquear la interfaz.

## Fase 3 — Teleprompter superpuesto a la cámara

### Objetivo
Que el usuario se vea a sí mismo y lea el texto cerca de la lente.

### Tareas

- Crear `TeleprompterOverlay` como capa sobre la vista de cámara.
- Mantener el texto en una región configurable próxima a la lente.
- Permitir:
  - Tamaño de letra.
  - Familia tipográfica.
  - Negrita.
  - Color.
  - Fondo transparente, semitransparente o sólido.
  - Ancho de columna.
  - Espaciado de líneas.
  - Alineación.
  - Línea guía.
  - Márgenes.
  - Espejo horizontal del texto.
  - Posición vertical y horizontal.
  - Inversión de la interfaz para accesorios de cristal reflectante.
- Añadir dos modos:
  - **Lectura**: texto grande, controles mínimos.
  - **Cámara**: vídeo y teleprompter visibles con controles.
- Implementar desplazamiento suave independiente de la frecuencia de refresco.
- Usar tiempo monotónico y velocidad en palabras por minuto cuando sea posible, no solo píxeles arbitrarios.
- Añadir marcadores y salto a párrafos.
- Permitir pausar, reanudar, reiniciar y desplazarse manualmente.

### Criterios de aceptación

- El texto es legible sobre fondos claros y oscuros.
- El usuario puede colocar el texto cerca de la cámara sin ocultar completamente su rostro.
- La velocidad se mantiene estable durante varios minutos.
- Los atajos actuales siguen funcionando y también existen botones visibles.

## Fase 4 — Controles, cuenta regresiva y control remoto

### Tareas

- Mantener Space, flechas, Ctrl/Shift, Home/R, +/-, F, O, G, Q y V, documentándolos en la interfaz.
- Añadir botones grandes para Play/Pausa, velocidad, reinicio y salto.
- Cuenta regresiva configurable: 0, 3, 5 o 10 segundos.
- Añadir pedal USB/HID opcional si se puede implementar sin depender de hardware propietario.
- Mejorar el servidor local:
  - Vincularlo por defecto a la red local solo cuando el usuario lo active.
  - Mostrar IP y puerto.
  - Generar QR.
  - Añadir token temporal o código de emparejamiento.
  - Desactivar el servidor al cerrar.
  - No exponerlo a Internet.
  - Validar comandos y limitar frecuencia.
- Control remoto móvil:
  - Play/Pausa.
  - Velocidad +/-.
  - Reinicio.
  - Progreso.
  - Cuenta regresiva.
  - Botón para iniciar y detener grabación.
  - Indicador de conexión.

### Criterios de aceptación

- El control remoto funciona en la misma red Wi-Fi sin nube.
- Un teléfono no autorizado no puede controlar la sesión si el emparejamiento está activado.
- La aplicación continúa funcionando si el teléfono se desconecta.

## Fase 5 — Captura de audio y grabación de vídeo

### Objetivo
Grabar cámara y micrófono sincronizados en un archivo reproducible.

### Tareas

- Implementar selección de micrófono mediante PipeWire/PulseAudio/ALSA según disponibilidad.
- Mostrar medidor de nivel y detectar saturación.
- Permitir elegir cámara y micrófono por separado.
- Añadir comprobación previa de audio y vídeo.
- Implementar `RecordingService` con cola de frames y cierre seguro.
- Grabar en formato intermedio fiable, preferentemente mediante FFmpeg cuando simplifique la sincronización.
- Guardar grabación original sin destruirla.
- Añadir nombre automático con fecha y hora.
- Mostrar duración, espacio disponible y estado de grabación.
- Permitir detener, cancelar y recuperar una grabación incompleta cuando sea posible.
- No mezclar la imagen del teleprompter en el vídeo final por defecto; el texto debe servir de ayuda durante la grabación.
- Ofrecer opción explícita para incrustar el texto si el usuario la solicita.

### Criterios de aceptación

- La grabación tiene audio y vídeo sincronizados.
- Cerrar la ventana durante una grabación no deja procesos FFmpeg huérfanos.
- El archivo original puede reproducirse con VLC y FFplay.
- Se informa al usuario antes de grabar si no hay micrófono o espacio suficiente.

## Fase 6 — Revisión y editor no destructivo

### Tareas

- Crear reproductor de revisión con controles de reproducción.
- Mostrar miniatura, duración y tamaño del clip.
- Permitir marcar inicio/fin y eliminar segmentos.
- Añadir recorte de principio y final.
- Añadir eliminación de pausas/silencios como función opcional, siempre con vista previa.
- Mantener edición no destructiva mediante una lista de segmentos en `project.json`.
- Permitir volver a grabar solo un segmento.
- Añadir deshacer/rehacer.
- No destruir el original hasta que el usuario lo solicite expresamente.

## Fase 7 — Subtítulos automáticos

### Tareas

- Mantener Vosk como backend local ligero opcional.
- Añadir backend opcional basado en Whisper/faster-whisper si se puede instalar y ejecutar de forma razonable en Debian 13.
- Permitir elegir idioma y modelo.
- Generar subtítulos con marcas de tiempo.
- Importar/exportar `.srt` y `.vtt`.
- Editar manualmente texto y tiempos.
- Resaltar palabras o frases.
- Elegir posición, tipografía, color, fondo y animación sencilla.
- Permitir subtítulos como pista editable y como incrustación final.
- Procesar en segundo plano y mostrar progreso, cancelación y tamaño del modelo.
- No descargar modelos sin consentimiento claro del usuario.

### Criterios de aceptación

- Un vídeo en español produce un `.srt` revisable.
- Los errores de reconocimiento se pueden corregir antes de exportar.
- El programa explica si el modelo no está instalado.

## Fase 8 — Branding y edición visual

### Tareas

- Crear Kit de Marca local:
  - Logo.
  - Colores.
  - Tipografías disponibles.
  - Intro.
  - Outro.
  - Nombre y datos de contacto.
- Añadir logo como superposición con posición y opacidad.
- Añadir títulos, subtítulos y lower thirds.
- Añadir imágenes y clips B-roll locales.
- Añadir biblioteca opcional de recursos libres, sin descargar contenido sin autorización.
- Añadir música local con control de volumen y fundido.
- Normalizar niveles de audio con FFmpeg cuando proceda.
- Añadir relación de aspecto:
  - Vertical 9:16.
  - Horizontal 16:9.
  - Cuadrado 1:1.
- Añadir previsualización de recorte para redes sociales.
- Añadir autozoom simple basado en cortes o posiciones, sin prometer seguimiento facial hasta implementar una solución fiable.

## Fase 9 — Funciones de IA opcionales y locales

### Tareas

- Asistente de guiones:
  - Crear borrador desde tema.
  - Ajustar tono.
  - Resumir.
  - Cambiar duración.
  - Crear título, descripción y etiquetas.
- Diseñar la integración por adaptadores:
  - Backend local.
  - Backend HTTP elegido por el usuario.
  - Ningún proveedor obligatorio.
- Mostrar siempre si el texto sale del ordenador.
- Solicitar consentimiento antes de enviar guiones, audio, vídeo o imágenes.
- No presentar como disponible una función de avatar, clonación de voz, corrección ocular o generación de vídeo hasta que esté implementada, probada y documentada.
- Si se implementa clonación de voz o avatar, incluir controles de consentimiento, borrado de modelos y advertencias contra suplantación.

## Fase 10 — Exportación y publicación

### Tareas

- Crear perfiles de exportación:
  - YouTube: 16:9.
  - TikTok/Reels/Shorts: 9:16.
  - LinkedIn: 16:9 o 1:1.
  - Archivo maestro de alta calidad.
- Usar FFmpeg con parámetros documentados.
- Permitir elegir contenedor, códec, resolución, FPS, bitrate y carpeta.
- Mostrar estimación de tamaño cuando sea posible.
- Validar que el archivo final exista, tenga tamaño razonable y pueda abrirse.
- Generar miniatura opcional.
- Copiar título, descripción y hashtags al portapapeles o guardarlos en un `.txt`/`.json`.
- No integrar publicación directa en redes hasta estudiar sus APIs, autenticación, límites y cambios de políticas.
- Como primera versión, ofrecer exportación local y apertura de la carpeta de salida.

## Fase 11 — Calidad, pruebas y accesibilidad

### Pruebas unitarias

- Configuración y migraciones.
- Cálculo WPM y duración.
- Conversión de rutas.
- Proyecto y recuperación.
- Segmentos de edición.
- Generación de subtítulos.
- Construcción de comandos FFmpeg.
- Validación de cámaras y micrófonos.

### Pruebas de integración

- Cámara integrada.
- Cámara USB.
- Micrófono USB.
- Cambio de cámara durante la sesión.
- Grabación de 1, 5 y 30 minutos.
- Desconexión de cámara.
- Desconexión de micrófono.
- Wayland y X11.
- Escalas de pantalla HiDPI.
- Guiones UTF-8 largos.
- Red local y teléfono remoto.

### Accesibilidad

- Atajos configurables.
- Navegación por teclado.
- Etiquetas accesibles para controles.
- Contraste comprobable.
- Tamaño de controles suficiente para uso durante grabación.
- Mensajes de error comprensibles.
- Interfaz inicial en español, preparada para traducciones con Qt Linguist.

### Herramientas

- `pytest` y `pytest-qt`.
- `ruff`.
- `mypy` gradual.
- `pre-commit` opcional.
- Cobertura en módulos críticos.
- Pruebas en una máquina real Debian 13, no solo en mocks.

## Fase 12 — Distribución Linux

### Tareas

- Crear instalación reproducible con `pyproject.toml`.
- Mantener `requirements.txt` y `requirements-dev.txt` separados.
- Documentar instalación con paquetes Debian y con entorno virtual.
- Crear archivo `.desktop` e icono.
- Evaluar paquete `.deb` con `dpkg-buildpackage` o equivalente.
- Mantener AppImage como distribución opcional, sin ocultar dependencias de cámara y FFmpeg.
- Incluir modelos de voz por descarga separada y documentada.
- No incluir modelos grandes innecesariamente en el ejecutable.
- Añadir comprobación de versión y migración de proyectos.

## 7. Reglas de implementación para el Agente de IA

1. Trabajar por fases pequeñas y compilables.
2. Antes de cambiar un módulo, leer su código y sus pruebas.
3. No eliminar una función existente sin reemplazo compatible o migración documentada.
4. No crear pseudocódigo presentado como código terminado.
5. Cada tarea debe terminar con pruebas ejecutadas y resultado registrado.
6. No usar llamadas de red para funciones locales básicas.
7. No añadir dependencias solo por comodidad si una biblioteca Debian adecuada ya existe.
8. Toda operación pesada debe ejecutarse fuera del hilo principal.
9. Nunca actualizar widgets Qt directamente desde un hilo de trabajo; usar señales.
10. Liberar cámara, micrófono, archivos y procesos externos en rutas normales y excepcionales.
11. Validar entradas de usuario y rutas de proyecto.
12. Usar rutas relativas en proyectos y recursos instalados localmente.
13. Separar archivos originales, temporales y exportados.
14. Pedir confirmación antes de borrar originales o sobrescribir exportaciones.
15. Documentar limitaciones reales de hardware y sistema.
16. Usar nombres propios del proyecto, por ejemplo `Teleprompter`, `BigPrompt` o el nombre que confirme el mantenedor.
17. Mantener licencia MIT si el propietario del repositorio la confirma.
18. **Regla de instalación de paquetes (obligatoria)**: cuando el desarrollo requiera instalar un paquete nuevo (`apt`, `pip` o cualquier otro gestor), el agente debe **detener el proceso inmediatamente y avisar al mantenedor** indicando el nombre exacto del paquete y el comando de instalación. El mantenedor es la única persona que puede instalar paquetes porque debe introducir su contraseña de administrador. El agente nunca debe intentar instalar paquetes por sí mismo, ni pedirlos de forma indirecta. Mientras el paquete no esté instalado y confirmado por el mantenedor, el agente debe limitarse a tareas que no dependan de él.

## 8. Formato de cada entrega del Agente

Para cada fase, el agente debe informar:

```text
Fase:
Objetivo:
Archivos modificados:
Archivos nuevos:
Dependencias añadidas:
Decisiones técnicas:
Limitaciones conocidas:
Pruebas ejecutadas:
Resultado de las pruebas:
Cómo ejecutar:
Siguiente tarea recomendada:
```

## 9. Orden recomendado del MVP

El MVP debe detenerse después de completar estas funciones:

- PyQt6 modular.
- Proyecto y guion UTF-8.
- Selección de cámara integrada/USB.
- Vista previa en directo.
- Texto superpuesto y desplazamiento.
- Cuenta regresiva.
- Grabación de cámara y micrófono.
- Revisión y recorte básico.
- Exportación local con FFmpeg.
- Control remoto móvil seguro en la red local.
- Documentación en español.
- Pruebas de hardware y software.

No comenzar con avatares, publicación automática o IA generativa antes de que el MVP grabe y exporte correctamente.

## 10. Definición de terminado

Una función se considera terminada solamente cuando:

- Está implementada con código real.
- Está integrada en la interfaz.
- Tiene manejo de errores.
- Tiene al menos una prueba apropiada.
- Está documentada en español.
- Funciona en Debian 13 en una prueba reproducible.
- No bloquea la interfaz.
- Libera correctamente sus recursos.
- No rompe funciones existentes.
- La limitación, si existe, aparece explícitamente en la interfaz o documentación.

## 11. Primera orden para el Agente de IA

Comienza así:

1. Audita el repositorio y enumera sus archivos y responsabilidades.
2. Ejecuta las pruebas existentes.
3. Comprueba qué paquetes están disponibles en Debian 13.
4. Propón una migración mínima de la estructura actual hacia la arquitectura indicada.
5. Implementa únicamente la Fase 0.
6. Ejecuta las pruebas y muestra los cambios.
7. Espera la aprobación del mantenedor antes de continuar con la Fase 1.

El objetivo no es producir una herramienta Linux nativa, local, verificable y mantenible que resuelva primero el flujo esencial: **guion → cámara → lectura superpuesta → grabación → revisión → exportación**.
