# Política de seguridad

## Versiones soportadas

El proyecto evoluciona rápidamente. Para reportes de seguridad se considera soportada la **release pública más reciente**.

## No publiques vulnerabilidades explotables en Issues

Si una vulnerabilidad puede exponer una cuenta Xiaomi, token miIO, dispositivo, mecanismo de actualización o control remoto del robot, no publiques los detalles en un Issue normal.

La vía preferida es **GitHub Private Vulnerability Reporting** mediante **Security → Report a vulnerability** cuando esa opción esté habilitada en el repositorio.

GitHub también permite usar Repository Security Advisories para discutir y corregir vulnerabilidades de forma privada antes de su divulgación.

## Qué incluir en un reporte privado

- versión afectada;
- impacto realista;
- precondiciones;
- pasos mínimos para reproducir;
- evidencia técnica saneada;
- propuesta de mitigación, si existe.

No incluyas datos de terceros.

## Secretos

Nunca compartas públicamente:

- contraseña Xiaomi;
- token miIO;
- cookies o credenciales Cloud;
- URLs FDS firmadas completas;
- claves derivadas;
- archivos de configuración personales sin sanear.

Si un secreto real se publica, debe considerarse comprometido y rotarse/revocarse cuando sea posible.

## Seguridad del repositorio

El proyecto incluye:

- **CODEOWNERS** para marcar los archivos sensibles como responsabilidad del mantenedor;
- **CodeQL** para análisis estático del código Python;
- **Dependabot** para dependencias Python y GitHub Actions;
- **secret scanning** de GitHub en el repositorio público;
- hashes SHA-256 para releases;
- smoke tests antes de publicar instaladores.

Para una protección efectiva de `main`, se recomienda además activar una ruleset/branch protection que requiera Pull Request, status checks y revisión del Code Owner.

## Almacenamiento local

La aplicación no pretende almacenar la contraseña de Xiaomi. Los tokens persistentes se protegen con Windows DPAPI cuando corresponde.

## Red local

El robot es un dispositivo de red. No expongas sus puertos o servicios directamente a Internet. La aplicación está pensada para operar dentro de una LAN confiable y utilizar Xiaomi Cloud sólo cuando una función lo requiera.

## Actualizaciones

Instalá builds desde la sección **Releases** del repositorio. Cada release oficial publica el instalador y su SHA-256.

Objetivo futuro: firma Authenticode del instalador y endurecimiento adicional de la cadena de suministro.

## Dependencias

Las dependencias de terceros se enumeran en `requirements.txt` y `THIRD_PARTY_NOTICES.md`. Un problema originado en una dependencia puede requerir coordinación con el proyecto upstream.

## Modelo de amenazas

Ver [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md).
