# Aspiradora Xiaomi

Aplicación de escritorio para Windows para controlar una **Xiaomi Robot Vacuum E10** (`xiaomi.vacuum.b112`) desde una PC en la misma red local.

## Funciones de la primera versión

- Estado y batería en tiempo real.
- Iniciar limpieza en modo aspirar, aspirar + trapear o solo trapear.
- Detener limpieza y enviar el robot a la base.
- Ajustar potencia de succión (1–4) y nivel de agua (0–3).
- Ver tiempo y área de la limpieza actual/última.
- Estado del depósito y la mopa.
- Vida útil de cepillo lateral, cepillo principal, filtro HEPA y mopa.
- Control manual direccional.
- Vinculación mediante cuenta Xiaomi para obtener IP/token cuando la cuenta lo permita, con ingreso manual como alternativa.
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

No subas tokens, contraseñas ni archivos de configuración personales al repositorio. El token se almacena únicamente en el perfil local de Windows y se cifra con DPAPI.

## Compatibilidad

Objetivo inicial: Windows 10/11 x64 y Xiaomi Robot Vacuum E10 (`xiaomi.vacuum.b112`).

## Licencias de terceros

Este proyecto utiliza `python-miio`, proyecto comunitario licenciado bajo GPL-3.0. Consultá `THIRD_PARTY_NOTICES.md` para detalles.
