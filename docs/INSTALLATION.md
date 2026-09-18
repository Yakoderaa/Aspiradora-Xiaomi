# Instalación y primeros pasos

## Requisitos

- Windows 10 u 11 de 64 bits.
- Xiaomi Robot Vacuum E10 (`xiaomi.vacuum.b112`).
- PC y aspiradora accesibles dentro de la misma red local.
- Conexión a Internet para vinculación, Xiaomi Cloud cuando sea necesaria y actualizaciones.

La PC puede usar Ethernet y el robot Wi‑Fi. Lo importante es que el router no aísle ambos dispositivos entre sí.

## Descargar

Usá siempre la página de **[GitHub Releases](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases/latest)**.

La release publica dos archivos:

- `Aspiradora-Xiaomi-Setup.exe`
- `Aspiradora-Xiaomi-Setup.exe.sha256`

El segundo contiene el SHA-256 del instalador y permite comprobar que el archivo descargado es exactamente el publicado por el workflow del proyecto.

## Instalar

Ejecutá `Aspiradora-Xiaomi-Setup.exe` y seguí el instalador.

Actualmente los builds públicos no utilizan un certificado comercial de firma de código. Dependiendo de la reputación del archivo y de la configuración de Windows, SmartScreen o un antivirus pueden pedir confirmación adicional. El proyecto intenta reducir falsos positivos mediante un paquete PyInstaller `onedir`, pero ningún proyecto sin firma puede garantizar que no aparezcan advertencias.

## Vincular el E10

La aplicación admite el flujo de vinculación implementado para obtener la información necesaria de Xiaomi y también permite configuración manual cuando corresponde.

La contraseña de Xiaomi no se persiste. El token local, cuando se guarda, se protege con **Windows DPAPI**, por lo que queda ligado al perfil de Windows del usuario.

## Red local

Para control LAN:

```text
PC ── Ethernet o Wi‑Fi ── Router ── Wi‑Fi 2.4 GHz ── E10
```

Si el robot aparece conectado pero no responde:

1. Confirmá que PC y E10 están en la misma LAN.
2. Desactivá temporalmente aislamiento de clientes/AP isolation si tu router lo utiliza.
3. Comprobá que la IP del robot no haya cambiado.
4. Cerrá y volvé a abrir la aplicación.
5. Usá el diagnóstico de la aplicación antes de publicar información en un issue.

## Actualizaciones

La aplicación consulta GitHub Releases para detectar versiones nuevas. El actualizador descarga el instalador correspondiente, comprueba el SHA-256 publicado y ejecuta la actualización.

## Desinstalación y datos locales

La aplicación almacena configuración y datos de trabajo dentro del perfil local de Windows. Los datos de mapa propios pueden residir en:

```text
%LOCALAPPDATA%\Aspiradora Xiaomi\
```

Antes de borrar manualmente esa carpeta, exportá cualquier información que quieras conservar.

## Soporte

Si encontrás un problema reproducible, usá las plantillas de **Issues** del repositorio. Nunca adjuntes contraseñas, tokens, cookies, URLs FDS firmadas ni configuraciones con secretos.
