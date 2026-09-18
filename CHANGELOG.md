# Changelog

Este archivo resume **hitos importantes**, no cada build interno. Para el detalle de cada publicación consultá [GitHub Releases](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases).

## Unreleased

### Documentación

- Nueva portada del proyecto.
- Documentación separada de instalación, mapeo, arquitectura y roadmap.
- Plantillas de issues y Pull Requests.
- Política de seguridad y guía de contribución.
- Builds de release excluidos para cambios exclusivamente documentales.

## V68 · 0.1.295

- El fin de Paso 1 deja de depender de que `sweep-type` publique EDGE=2.
- Se reconoce el final mediante movimiento/salida de base seguido de retorno, carga o inactividad estable.
- Comprobación final antes de declarar timeout.
- Integración con la transición automática base → Paso 2.

## V67 · 0.1.294

- Watchdog LAN dedicado para encadenar Paso 1 → base → Paso 2.
- Confirmación por estado operativo y estado de carga.
- Protección one-shot para evitar iniciar Paso 2 dos veces.

## V66 · 0.1.293

- Soporte del quirk de respuesta vacía documentado para `xiaomi.vacuum.b112`.
- Respuestas con `id + exe_time` pueden reconocerse como ACK fuerte cuando cumplen las condiciones seguras.

## V64–V65

- Adopción de `build-map-ii` para armar un mapa nuevo.
- Corrección de la interpretación de `map-privacy`.
- Manejo de ACK de acciones MIoT que no incluyen `code=0`.

## V40–V60

- Investigación y decodificación del mapa B112.
- Rutas LAN/Cloud/FDS.
- Parsers IJAI/Xiaomi.
- Validación de grid y rechazo de geometría incoherente.
- Diagnóstico estructurado de frescura, hashes y fuentes de mapa.

## Primeras versiones

- Control local del E10.
- Interfaz Windows.
- Estado, batería, consumibles, base, agua y succión.
- Instalador, actualización automática y scheduler.
