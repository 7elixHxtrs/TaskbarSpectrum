# Taskbar Spectrum

Visualizador de espectro de audio para la **barra de tareas de Windows**, al estilo de [Cava](https://github.com/karlstav/cava) en Linux.

Captura lo que suena en tu PC (Spotify, YouTube, juegos, lo que sea) y dibuja barras animadas sobre tu barra de tareas, justo al lado de la bandeja del sistema.

> by: [7elixHxtrs](https://github.com/7elixHxtrs)

---

## ✨ Características

- 🔊 Captura el **audio del sistema** (WASAPI loopback), sin micrófono ni configuración.
- 📍 Detecta si tu barra de tareas está **arriba, abajo, a la izquierda o a la derecha**.
- 🖱️ **Icono en la bandeja** con menú y ventana de configuración en vivo.
- 🙈 Visibilidad inteligente:
  - Siempre visible
  - Ocultar en **pantalla completa** (juegos, video)
  - Ocultar con ventana **maximizada** o pantalla completa
  - Ocultar cuando **no suena nada**
- 🎨 Personalizable: color, ancho, alto (automático o manual), cantidad de barras, espacio entre barras, opacidad, posición, caída de las barras.
- 🚀 **Iniciar con Windows** (opcional).
- 💾 La configuración se guarda sola en `%APPDATA%\TaskbarSpectrum\config.json`.
- 🪶 Ligero: sin servicios en segundo plano ni dependencias raras.

---

## 📦 Instalación (usuarios)

1. Ve a la sección **[Releases](../../releases)** y descarga `TaskbarSpectrum-Setup.exe`.
2. Ejecútalo y sigue el asistente. Puedes elegir:
   - Iniciar el programa al encender el PC
   - Crear acceso directo en el escritorio
3. Listo. El visualizador aparece en tu barra de tareas y verás un icono en la bandeja.

> 💡 Windows suele esconder los iconos nuevos en el panel de la flecha `^`. Arrástralo a la barra para tenerlo siempre a mano.

> ⚠️ El instalador no está firmado digitalmente, así que Windows SmartScreen o algún antivirus pueden mostrar una advertencia la primera vez. Es normal en programas independientes.

### Uso

| Acción | Resultado |
|---|---|
| Doble clic en el icono de la bandeja | Abre la configuración |
| Clic derecho en el icono de la bandeja | Menú: configuración, mostrar/ocultar, reiniciar audio, iniciar con Windows, salir |
| Clic derecho sobre una barra del visualizador | Abre la configuración |

Si cambias de altavoces a auriculares con el programa abierto, usa **Reiniciar captura de audio** para que siga el nuevo dispositivo.

---

## 🛠️ Compilar desde el código fuente

Requisitos: **Windows 10/11** y **Python 3.9 o superior** (con el lanzador `py`).

### Opción rápida: crear el instalador

Haz doble clic en **`build.bat`**. Este script:

1. instala las dependencias,
2. genera el icono,
3. compila `dist\TaskbarSpectrum.exe` con PyInstaller,
4. crea `installer\TaskbarSpectrum-Setup.exe` con [Inno Setup](https://jrsoftware.org/isinfo.php) (lo instala con `winget` si no lo tienes).

### Ejecutar sin compilar

```bash
pip install -r requirements.txt
python taskbar_spectrum_app.py
```

---

## 🗂️ Estructura del proyecto

```
├── taskbar_spectrum_app.py   # la aplicación completa
├── make_icon.py              # genera icon.ico para el .exe y el instalador
├── installer.iss             # script del instalador (Inno Setup)
├── build.bat                 # compila el .exe y el instalador
├── requirements.txt
├── LICENSE
└── README.md
```

---

## ⚙️ Cómo funciona

1. **Captura:** [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) abre el dispositivo de salida predeterminado en modo *loopback* de WASAPI.
2. **Análisis:** una FFT de 2048 muestras con ventana Hann; el espectro se agrupa en bandas con escala logarítmica (40 Hz – 16 kHz) y se normaliza con auto-sensibilidad, como hace Cava.
3. **Dibujo:** una ventana de Tkinter sin bordes, transparente y siempre encima, colocada sobre la barra de tareas.
4. **Bandeja:** [pystray](https://github.com/moses-palmer/pystray) para el icono y el menú.

> Windows no permite incrustar widgets dentro de la barra de tareas de forma oficial, por eso el visualizador es una ventana flotante colocada encima de ella.

---

## 🩺 Solución de problemas

- **No se mueven las barras:** usa *Reiniciar captura de audio*. Verifica que el audio salga por el dispositivo predeterminado de Windows.
- **El visualizador queda en otro lugar:** ajusta *Distancia al borde derecho* y *Ajuste vertical* en la configuración.
- **Otros errores:** revisa el registro en `%APPDATA%\TaskbarSpectrum\app.log` y abre un *issue* con su contenido.

---

## 📄 Licencia

Distribuido bajo la licencia MIT. Consulta el archivo [`LICENSE`](LICENSE).

---

<p align="center">Hecho por <a href="https://github.com/7elixHxtrs">7elixHxtrs</a></p>
