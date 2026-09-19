# Changelog

Este archivo resume **hitos importantes**, no cada build interno. Para el detalle de cada publicación consultá [GitHub Releases](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases).

## Unreleased

### V96 · arranque tardío seguro + rendimiento

- Corrige el caso observado en V95 donde `10/24` tenía movimiento real (25 cambios / 26 puntos) pero V80 rechazaba toda la trayectoria y el mapa seguía en 0 puntos.
- El gate inicial de V79/V80 se unifica en **0,90 m** y ya no exige que la primera muestra útil llegue dentro de 0,35 m del dock.
- Una primera muestra tardía sólo se acepta después de **4 muestras continuas**; una discontinuidad superior a 0,40 m reinicia el gate en vez de inventar trayectoria.
- Antes de validar el arranque, V85 no puede crear un rebase persistente: las coordenadas permanecen en el marco físico `10/24 - base`.
- El worker LAN deja de multiplicar callbacks: existe un único temporizador pendiente y un único worker de lectura.
- Cloud nunca libera artificialmente un worker lento; no se crean hilos huérfanos/solapados. El intervalo de lectura pesada sube a 12 s.
- La cola de eventos de Tk se procesa con presupuesto por ciclo y los repintados del mapa se coalescen, reduciendo el lag al pulsar botones o mover la ventana.
- F12 V96 muestra motivo del gate inicial, discontinuidades, rebases pre-gate bloqueados, polls LAN, starts Cloud reales, stalls y renders coalescidos.


### V95 · recuperación del mapa vivo + controles globales

- La barra superior prioriza el estado físico real del E10 sobre faults residuales cuando está retornando/cargando/limpiando; un `fault=2105` ya no reemplaza `status=4` por “Error”.
- El fault residual se conserva en F12 para diagnóstico.
- Identidad de audio de Windows explícita como **Aspiradora**: AppUserModelID, metadatos del ejecutable y nombre de sesión Core Audio para que SteelSeries Sonar no la muestre como “unknown”.

- Corrige el caso observado en F12 donde el E10 estaba físicamente en `status=5` pero la app seguía con **0 frames V92, 0 puntos 10/24 y 0 lecturas de mapa**, mientras Mi Home sí actualizaba.
- Durante un mapeo, `status 5/6/7` ahora puede despertar directamente el lector Cloud aunque la telemetría LAN todavía no haya entregado ninguna pose.
- El loop de mapa LAN deja de morir si encuentra un worker ya activo: reprograma el siguiente intento en vez de abandonar el sondeo.
- Watchdog de sólo lectura para LAN y Cloud: si una consulta queda colgada demasiado tiempo, se libera el gate y se permite una lectura nueva sin congelar toda la sesión.
- Al confirmar el START de mapeo se rearman explícitamente ambos streams, LAN + Cloud.
- F12 V95 muestra edades de actividad, workers activos, recuperaciones, resets por timeout, polls locales y kicks Cloud.
- La barra superior incorpora **Iniciar limpieza** y **Volver a base** siempre visibles.
- **Iniciar limpieza** reaplica modo, succión y agua actualmente seleccionados antes de arrancar la limpieza normal.
- La limpieza normal queda bloqueada durante un mapeo activo para no pisar la sesión.
- Esta versión se empaqueta desde `main_v95.py`, incluyendo realmente V93 y V94 dentro del EXE.


### V92 · layouts 2bpp + acumulación temporal

- Conserva la cabecera B112 real de V91: **3628 B = 28 B de cabecera + 3600 B de grid**.
- Ya no supone que cada byte contiene cuatro celdas horizontales.
- Prueba **28 layouts físicos**: horizontal4 MSB/LSB, vertical4 MSB/LSB y bloque 2×2 con las 24 permutaciones locales.
- Cada layout se prueba con las siete máscaras 2bpp: `nonzero`, `v1`, `v2`, `v3`, `v12`, `v13`, `v23`.
- Total: **196 candidatos por frame**.
- Acumula por candidato los hashes nuevos de una sesión mediante unión binaria, para detectar mapas publicados como frames/deltas.
- Reinicia la acumulación al comenzar un mapeo nuevo o ante un salto temporal incompatible.
- El ranking combina validez V57, componente mayor, ratio, adyacencia y distancia a la base.
- **V57 sigue siendo obligatorio**: ningún candidato actual ni acumulado se renderiza si no pasa la coherencia espacial.
- Corrige el sentinela `10/22=255_255`: nunca vuelve a convertirse en una base geométrica de 51 m; para grid usa el fallback B112 `60_60`.
- F12 muestra mejor frame, mejor acumulado, seleccionado, cantidad de hashes y top de layouts.
- No modifica `RAW_TO_METERS`, antiatasco, continuidad, retorno ni las protecciones V90.

### V91 · cabecera B112 real + reconstrucción de superficie

- Corrige el parser del payload post-hex observado en el E10: `type8 + version8 + len16be`.
- Reconoce la estructura real de **3628 bytes = 28 bytes de cabecera + 3600 bytes de grid 120×120 2bpp**.
- La cabecera observada acepta tipos variables (por ejemplo 0x09/0x0B/0x0D), versión 1 y longitud 24.
- El decoder prueba orden MSB/LSB y máscaras de capa `1`, `2`, `3`, `1+2`, `1+3`, `2+3` y `nonzero`.
- **V57 sigue siendo obligatorio**: un grid incoherente jamás se persiste ni se dibuja.
- El grid candidato usa resolución de **0,20 m**. Por seguridad, V91 no cambia todavía `RAW_TO_METERS` de V77/V85.
- Si no hay grid Xiaomi válido, el fallback visual usa radio físico de 0,18 m, interpola entre muestras, cierra huecos cortos entre carriles y rellena sólo huecos completamente encerrados.
- El viewport y las miniaturas incluyen la superficie reconstruida completa.
- F12 compara área/celdas del fallback anterior con V91, bounding box y densidad de cobertura.
- Se conservan sin cambios el gate de START/salida física de V90 y el recorrido invisible de V89.

### V90 · START real y cierre de dock por sesión

- Corrige la carrera que cerraba el mapeo con `tiempo 0.0 s` cuando llegaban puntos `10/24` mientras el robot todavía informaba `status=4`.
- `status=4` antes de `v74_mapping_started` ya no puede finalizar una sesión.
- Después del START, la app exige observar una salida física real del dock mediante `status 5/6/7`.
- Sólo después de esa salida un `status=3/4` puede considerarse retorno real y cerrar el mapeo.
- Los retornos/status tempranos quedan bloqueados y contabilizados en F12.
- Los puntos `10/24` tempranos se conservan para diagnóstico, pero no son prueba suficiente de salida física.
- Watchdog de START de 60 s: si no hay confirmación, cancela el intento, ejecuta `stop + dock` y evita etiquetarlo falsamente como “mapeo incompleto”.
- Un START tardío u obsoleto se descarta y no puede reactivar el watcher.
- Se conserva V89 sin cambios visuales: recorrido oculto, sólo perímetro + relleno + base + robot.

### V89 · mapa limpio sin recorrido visible

- Se ocultan las líneas internas del recorrido en el mapa grande y en las cuatro miniaturas.
- La presentación conserva únicamente **perímetro + relleno + base + robot**.
- La trayectoria física no se elimina ni modifica: sigue guardada completa en `LocalMapStore`.
- Cobertura, completitud, antiatasco, continuidad V85/V86 y demás cálculos siguen usando todos los puntos.
- F12 añade cantidad de puntos, segmentos, longitud y extremos del recorrido oculto.
- La leyenda deja de mostrar **Recorrido** porque esa capa ya no se representa visualmente.
- Se conserva la geometría Xiaomi validada/persistente de V88 y su fallback estimado cuando no hay grid real válido.

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
