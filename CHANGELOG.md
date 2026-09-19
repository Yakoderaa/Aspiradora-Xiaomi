# Changelog

Este archivo resume **hitos importantes**, no cada build interno. Para el detalle de cada publicación consultá [GitHub Releases](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases).

## Unreleased

### V88 · geometría Xiaomi validada y persistente

- El mapa grande y las miniaturas usan la rejilla interna Xiaomi cuando V57 confirma que es espacialmente coherente.
- La geometría nativa se guarda dentro de cada mapa local y sobrevive reinicios/cambios de mapa.
- Corrección del sentinela de base `255_255`: si queda fuera de la rejilla B112, el renderer usa el centro físico `60_60`.
- Los límites de zoom/Zoom Extents incluyen la planta Xiaomi completa, no sólo el recorrido del robot.
- La leyenda fija pasa a **Mapa Xiaomi / Mapa estimado + Recorrido**, acorde al mapeo actual de una sola pasada.
- Si no hay grid Xiaomi válido, V88 conserva el fallback de V87 pero a resolución de 10 cm, reduciendo la deformación visual.
- V85/V86 siguen controlando trayectoria, continuidad, antiatasco, dock físico y ETA; V88 no altera esa lógica.
- La personalización de voz sigue fuera de esta versión y queda como opción futura.

### V87 · modos de limpieza nativos

- Botones **Limpiar bordes** y **Espiral** en el panel de limpieza.
- Uso de `sweep-type=2` para bordes y `sweep-type=4` para espiral/punto.
- La limpieza normal fuerza `sweep-type=0` para no heredar el patrón anterior.
- Los patrones especiales respetan el modo seleccionado: aspirar, aspirar + trapear o trapear.
- Se conserva el cierre V86: el aviso de mapeo sólo aparece una vez confirmado físicamente el dock.
- Nuevo renderer de mapa inspirado en Mi Home: superficie explorada continua, contorno exterior azul, sin grilla visible, base verde y robot orientado.
- El cambio visual no modifica coordenadas, cobertura ni la lógica física del mapeo.
- Personalización de voz: queda fuera de V87 y se evaluará como función futura mediante paquetes compatibles.


### Presentación

- Portada profesional con galería de fotografías oficiales del Xiaomi E10.
- Badges de release, build y CodeQL.
- Documentación separada de instalación, mapeo, arquitectura, roadmap y FAQ.

### Seguridad

- CodeQL para Python.
- Dependabot para Python y GitHub Actions.
- CODEOWNERS con el mantenedor como propietario.
- Modelo de amenazas y guía de endurecimiento de GitHub.
- Política de divulgación coordinada de vulnerabilidades.
- Builds de release excluidos para cambios exclusivamente documentales/de seguridad del repositorio.

### Propiedad intelectual

- Aviso de copyright.
- Guía de DNDA, marca y evaluación de patentabilidad.
- Política temporal para mantener una cadena clara de titularidad de contribuciones.

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
