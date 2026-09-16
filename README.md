# Aspiradora Xiaomi

Aplicación de escritorio para Windows para controlar una **Xiaomi Robot Vacuum E10** (`xiaomi.vacuum.b112`) desde una PC en la misma red local.

## Interfaz

La interfaz principal está inspirada en la organización de Xiaomi Home: navegación lateral, mapa como elemento central, tarjetas de estado y controles rápidos de limpieza, mopa, succión y agua. No se copian recursos gráficos ni código de Xiaomi Home.

## Mapa local propio

La aplicación puede crear un mapa **desde cero en la PC**, sin descargar la imagen de mapa de Mi Home/Xiaomi Cloud.

- Al elegir **Mapa local → Crear desde cero**, se borra únicamente el mapa guardado por esta aplicación.
- El E10 realiza un recorrido con agua y succión apagadas.
- La PC consulta directamente por la red local las propiedades MIoT de trayectoria (`10/5`), posición del robot (`10/24`) y posición de la base (`10/22`).
- La trayectoria se guarda en `%LOCALAPPDATA%\Aspiradora Xiaomi\local_map.json`.
- El plano aproximado se reconstruye a partir de la superficie recorrida por el robot.
- Se pueden dibujar habitaciones locales manualmente sobre el mapa y guardarlas sólo en la PC.
- Se puede hacer clic en un punto del mapa para iniciar una limpieza puntual o limpiar una habitación local como zona rectangular.

El E10 no expone por LAN una imagen completa con paredes equivalente a la que muestra Xiaomi Home. Por eso el mapa local se reconstruye a partir de su trayectoria y posiciones, en lugar de descargar el archivo propietario de Xiaomi Cloud.

## Funciones

- Estado y batería en tiempo real.
- Iniciar limpieza en modo aspirar, aspirar + trapear o solo trapear.
- Activar o desactivar el uso de la mopa.
- Detener limpieza y enviar el robot a la base.
- Ajustar potencia de succión y nivel de agua.
- Ver tiempo y área de la limpieza actual/última.
- Estado del depósito y la mopa física.
- Vida útil de cepillo lateral, cepillo principal, filtro HEPA y mopa.
- Control manual direccional.
- Mapa local generado en la PC.
- Habitaciones locales dibujadas por el usuario.
- Limpieza por punto y por zona desde el mapa.
- Vinculación mediante QR de Xiaomi para obtener IP/token cuando sea necesario, con ingreso manual como alternativa.
- Token guardado cifrado con Windows DPAPI. La contraseña de Xiaomi no se guarda.
- Actualizaciones automáticas desde GitHub Releases.

## Instalación

Descargá `Aspiradora-Xiaomi-Setup.exe` desde la última Release del repositorio. La aplicación se instala para el usuario actual y no necesita ejecutarse en un navegador.

## Red

La PC puede estar conectada al router por Ethernet y el robot por Wi‑Fi. Ambos deben poder comunicarse dentro de la misma red local. El E10 usa Wi‑Fi de 2.4 GHz.

## Desarrollo

La interfaz está escrita en Python/Tkinter y el control local usa `python-miio`/MIoT. GitHub Actions genera un paquete `onedir` con PyInstaller y luego un instalador con Inno Setup. Se evita el modo PyInstaller `onefile` para reducir falsos positivos de antivirus.

Cada ejecución de publicación genera una versión `0.1.<run>` y una GitHub Release. La app consulta periódicamente la última Release; si encuentra una versión nueva, descarga el instalador, verifica su SHA-256 y ejecuta la actualización silenciosa.

## Seguridad

No subas tokens, contraseñas ni archivos de configuración personales al repositorio. El token se almacena únicamente en el perfil local de Windows y se cifra con DPAPI. El mapa local se guarda sólo en la PC.

## Compatibilidad

Objetivo inicial: Windows 10/11 x64 y Xiaomi Robot Vacuum E10 (`xiaomi.vacuum.b112`).

## Licencias de terceros

Este proyecto utiliza `python-miio`, proyecto comunitario licenciado bajo GPL-3.0. Consultá `THIRD_PARTY_NOTICES.md` para detalles.
