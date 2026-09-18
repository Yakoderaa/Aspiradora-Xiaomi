# Contribuir

Gracias por interesarte en Aspiradora Xiaomi.

El proyecto trabaja con un dispositivo real y un protocolo que contiene comportamientos específicos del firmware, por lo que una contribución útil debe priorizar reproducibilidad y seguridad.

## Antes de abrir un issue

Buscá issues existentes y comprobá que estés usando una release reciente.

Para bugs, incluí:

- versión de la aplicación;
- Windows 10/11 y arquitectura;
- modelo exacto del robot;
- qué estabas haciendo;
- resultado esperado;
- resultado real;
- pasos para reproducir;
- diagnóstico F12 saneado cuando sea relevante.

**Nunca publiques** token, contraseña, cookies, URLs FDS firmadas, claves, datos de cuenta ni archivos de configuración personales.

## Desarrollo local

```powershell
git clone https://github.com/Yakoderaa/Aspiradora-Xiaomi.git
cd Aspiradora-Xiaomi
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Pull Requests

1. Creá una rama a partir de `main`.
2. Limitá el PR a un objetivo claro.
3. No cambies simultáneamente protocolo, UI y build salvo que sea imprescindible.
4. Agregá o actualizá un smoke test si corregís un comportamiento del E10.
5. Explicá cómo verificaste el cambio.
6. No incluyas secretos ni dumps crudos de una cuenta Xiaomi.

## Tests

Como mínimo:

```powershell
python -m compileall -q src scripts
```

Los PR que modifican comportamiento del robot deberían ejecutar los smoke tests relacionados. El workflow de publicación ejecuta la suite acumulativa antes de generar una release.

## Cambios de protocolo

Cuando agregues soporte para una respuesta MIoT nueva:

- conservá la respuesta real en un fixture saneado;
- diferenciá ACK, error y respuesta ambigua;
- no autorices movimiento a partir de una heurística débil;
- evitá acciones destructivas para investigar;
- documentá el modelo/firmware al que aplica.

## Estilo

Preferimos código directo y fácil de diagnosticar. Los comentarios deben explicar el motivo de una decisión o quirk, no repetir lo que hace una línea.

## Documentación

Los cambios sólo de documentación no generan una nueva release de la aplicación.
