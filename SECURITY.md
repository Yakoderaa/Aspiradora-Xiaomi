# Política de seguridad

## Versiones soportadas

El proyecto evoluciona rápidamente. Para reportes de seguridad, se considera soportada la **release pública más reciente**.

## Reportar una vulnerabilidad

No publiques una vulnerabilidad que exponga tokens, credenciales o acceso a dispositivos como un issue público.

Si GitHub ofrece la opción **Security → Report a vulnerability** en el repositorio, utilizala para un reporte privado. Si esa opción no está disponible, contactá al mantenedor a través de su perfil de GitHub sin incluir secretos en mensajes públicos.

Incluí:

- versión afectada;
- impacto;
- pasos mínimos para reproducir;
- condiciones necesarias;
- propuesta de mitigación si la tenés.

## Secretos

Nunca compartas públicamente:

- contraseña Xiaomi;
- token miIO;
- cookies o credenciales Cloud;
- URLs FDS firmadas completas;
- claves derivadas;
- archivos de configuración personales sin sanear.

## Almacenamiento local

La aplicación no pretende almacenar la contraseña de Xiaomi. Los tokens persistentes se protegen con Windows DPAPI cuando corresponde.

## Red local

El robot es un dispositivo de red. Evitá exponer puertos o servicios de la aspiradora directamente a Internet. La aplicación está pensada para operar dentro de una LAN confiable y utilizar Xiaomi Cloud sólo cuando una función lo requiera.

## Dependencias

Las dependencias de terceros se enumeran en `requirements.txt` y `THIRD_PARTY_NOTICES.md`. Un reporte que afecte exclusivamente a una dependencia upstream puede requerir coordinación con ese proyecto.
