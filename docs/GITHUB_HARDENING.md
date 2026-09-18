# Endurecimiento de GitHub

Este documento separa las protecciones que ya viven en el repositorio de las opciones administrativas que debe activar el propietario desde la interfaz de GitHub.

## Ya incorporado al repositorio

- `.github/CODEOWNERS` con `@Yakoderaa` como responsable.
- CodeQL para Python.
- Dependabot para Python y GitHub Actions.
- `SECURITY.md`.
- modelo de amenazas.
- smoke tests antes de las releases.
- SHA-256 del instalador.
- releases generadas por GitHub Actions.
- documentación de propiedad intelectual.
- cambios documentales excluidos del workflow de release.

## Configuración recomendada en GitHub

### 1. Private Vulnerability Reporting

En el repositorio:

```text
Settings → Security / Code security and analysis → Private vulnerability reporting
```

Activarlo permite que un investigador reporte una vulnerabilidad sin publicarla en Issues.

### 2. Branch protection / Ruleset para `main`

Crear una regla para `main` y activar, como mínimo:

- Require a pull request before merging.
- Require status checks to pass.
- Require conversation resolution.
- Require review from Code Owners.
- Block force pushes.
- Block deletion.
- Si tu flujo lo permite, Require signed commits.

Para un repositorio personal, evaluá cuidadosamente si exigís una aprobación adicional porque el único Code Owner puede ser el mismo propietario.

### 3. Secret scanning y push protection

En repositorios públicos, GitHub ofrece secret scanning para múltiples tipos de credenciales. Verificá en **Security** que esté activo y habilitá push protection cuando la cuenta lo permita.

### 4. Dependabot alerts / security updates

Activá:

- Dependabot alerts.
- Dependabot security updates.

El archivo `.github/dependabot.yml` ya configura PRs semanales de actualización.

### 5. Autenticación de la cuenta

La seguridad del repositorio depende de la cuenta del propietario.

Recomendado:

- 2FA obligatorio.
- passkey o llave de seguridad como método fuerte.
- códigos de recuperación almacenados fuera de la PC principal.
- sesiones y aplicaciones OAuth revisadas periódicamente.
- tokens de GitHub con mínimo alcance y fecha de expiración.

### 6. Releases

Objetivo futuro:

- firma Authenticode del instalador;
- protección de tags de release;
- environment protegido para publicación;
- build reproducible / lockfile con hashes.

## Repositorio público vs privado

Un repositorio privado reduce la exposición futura, pero no puede retirar copias locales o forks que se hayan creado cuando el contenido era público.

Si en el futuro se desarrolla una innovación que se quiera evaluar para patente, conviene mantener **esa nueva parte** privada hasta definir la estrategia con un profesional.

## Qué no resuelve GitHub

GitHub no puede impedir que alguien copie material que ya vio públicamente. Las protecciones de branch/rulesets evitan cambios no autorizados en **tu repositorio**, pero no controlan copias externas.

Para propiedad intelectual ver [INTELLECTUAL_PROPERTY.md](INTELLECTUAL_PROPERTY.md).
