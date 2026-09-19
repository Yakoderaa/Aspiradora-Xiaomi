# Changelog

### V123 · whole-home preparado + trigger físico

- V122 confirmó que `7/3 set-room-clean(["",0,1])` es aceptado por el E10 pero puede dejarlo en `status=4` cuando acaba de volver al dock.
- La Fase 2 conserva primero la configuración whole-home por `7/3`.
- Se espera brevemente la salida física. Si el E10 pasa a `status 5/6/7`, no se envía nada más.
- Si continúa exactamente en `status=4`, se emite una única acción `2/3 start-only-sweep` para sacar el robot del dock.
- La transición V123 **no usa `2/1 start-sweep`**, evitando repetir la ruta V121 que quedó confinada a la habitación inicial.
- No se ejecuta otro `arm_new_map`/`build-map`, ni STOP/manual/recovery.
- F12 registra respuesta de prearm, estado antes del trigger, si se envió `2/3`, respuesta y método que finalmente produjo movimiento.
- Conserva V121/V122: primer dock intermedio, segundo dock final y rechazo de grids finales inválidos.


### V122 · Fase 2 whole-home por Sweep 7/3

- Corrige el patrón observado en V121: más de 16 m recorridos dentro de ~1,14 m alrededor de la base, con ida/vuelta repetido durante ~240 s.
- La Fase 2 deja de usar el START global genérico `2/1` / `2/3`.
- Después del dock intermedio, fija `sweep-type=0` y ejecuta una sola acción `7/3 set-room-clean(["", 0, 1])`.
- Los room ids vacíos conservan el objetivo de **toda la vivienda**; modo 0 pide limpieza normal en vez de Edge.
- No se ejecuta otro `arm_new_map` ni `build-map-ii`: se conserva la misma sesión iniciada antes del perímetro.
- No se reactiva el recovery heredado `STOP -> manual -> start_mapping_interior`, para no reiniciar el mapa de Mi Home.
- F12 V122 registra comando, respuesta, status y sweep-type de la nueva Fase 2.
- Conserva V121: primer dock = transición, segundo dock = final, y grids con `metrics.valid=False` no se guardan.


### V121 · perímetro → interior en la misma sesión Xiaomi

- El mapeo pasa a dos fases sin ejecutar un segundo `build-map-ii`.
- **Fase 1/2:** Edge recorre el perímetro completo y descubre puertas/límites.
- El primer `status=4` al volver del perímetro es un **dock intermedio**: no cierra `mapping_active`, no notifica fin y no dispara captura final.
- **Fase 2/2:** desde ese mismo dock se ejecuta `start_mapping_interior()` con sweep global, sin `arm_new_map()`.
- La salida física de Fase 2 se confirma por `status 5/6/7`; si no arranca, la sesión se detiene sin guardar el mapa parcial.
- Sólo el dock posterior a Fase 2 habilita las tres lecturas finales Xiaomi.
- Corrige el falso mapa final de **40 celdas** observado en V120: `_v107_choose_final_grid` rechaza cualquier frame con `metrics.valid=False`.
- F12 V121 muestra fase actual, transición, confirmación de Fase 2, cierres/capturas prematuras suprimidas y frames finales inválidos rechazados.
- Se reparan los separadores literales heredados del bloque de smoke tests para que V117–V121 se ejecuten como comandos independientes durante CI.


### V120 · exploración de vivienda en vez de limpieza global

- **Mapear vivienda** conserva `10/17 build-map-ii(mode=1)`, ECO y agua apagada.
- Después del build ya no ejecuta `start_mapping_interior()` ni un START global normal.
- La única orden de movimiento es `7/3 set-room-clean(["", 2, 1])`: habitaciones vacías = toda la vivienda, modo Edge, Start.
- Antes del comando fija `sweep-type=2` y limpia repetición heredada.
- El arranque sólo se acepta si el estado físico pasa a 5/6/7; si no, se aborta con error visible en vez de caer a una limpieza normal.
- No existe segunda fase automática ni segundo START.
- F12 V120 registra build, comando exacto, respuesta, status y sweep-type observados.
- Se mantiene V119: corredor repetido y falta temporal de área nueva no pueden finalizar el mapa ni mandarlo a la base.
- La vista provisional sigue fuera de prioridad; la geometría se juzga al capturar el mapa Xiaomi final en dock.


### V119 · mapeo completo sin cierre heurístico prematuro

- Corrige el retorno observado con habitaciones todavía sin recorrer: V81 consideraba “completo” el mapa por cobertura mínima + corredor repetido y ejecutaba `stop + dock`.
- Durante **Mapear vivienda**, `no-new-area` ya no puede finalizar la sesión ni enviar el robot a la base.
- Un corredor repetido ya no llama a `_v81_finish_complete` ni `_v81_stop_incomplete`; la sesión permanece abierta.
- Los recoveries clasificados como **corredor/sector repetido** se suprimen para priorizar la autorrecuperación del firmware y evitar reiniciar el sweep/Mi Home.
- La recuperación automática se conserva para una oscilación realmente estacionaria sin avance.
- El cierre normal queda reservado al retorno físico del propio E10 o a **Detener mapeo**.
- V118 deja de interpretar `status 5/6/7` como limpieza global cuando `mapping_active=True`.
- F12 V119 contabiliza cierres y recoveries heurísticos suprimidos.


### V118 · sesión física autoritativa + START único

- Corrige el desacople observado: el diagnóstico podía mostrar `limpieza global activa=False` mientras el E10 seguía en `status=5`.
- Una vez confirmado `status 5/6/7`, el controlador mantiene un candado físico independiente del worker de UI.
- El candado se libera inmediatamente en `status=4` real; `status 0/1` requiere seis lecturas consecutivas para evitar cierres por muestras transitorias.
- Mientras el candado está activo se bloquea cualquier segundo START global, bordes, espiral, habitación, zona o arranque de mapeo.
- El guard de mapeo ya no depende únicamente de `_targeted_clean_guard`; también respeta la sesión física.
- F12 registra órdenes de arranque, intentos bloqueados, transiciones de estado y divergencias entre estado físico y worker.
- Conserva V117: pose 10/24 viva sobre las 241 celdas sin modificar `native_grid`, y contador de `locate()` para investigar pitidos.


### V117 · aspiradora viva sobre el mapa Xiaomi guardado

- Corrige el caso observado en V116 donde la limpieza arrancaba y el mapa de 241 celdas permanecía intacto, pero la aspiradora desaparecía.
- Causa: V73 anulaba `robot` y `charging_base` cuando `mapping_active=False`, aunque 10/24 siguiera cambiando durante una limpieza normal.
- V117 captura 10/24 y 10/22 antes de esa capa y dibuja la pose como `(robot-base) × 0,10 m`.
- Aplica el mismo reflejo del eje Y usado por el grid final V107 para que la pose y la planta compartan marco.
- El seguimiento vivo es sólo un overlay: no escribe `native_grid`, no reconstruye la planta y no añade recorrido.
- En `status=4` el robot se fija al dock para ignorar telemetría residual.
- F12 registra raw 10/24, raw 10/22, pose convertida, cambios y renders.
- Se cuentan las llamadas `locate()`/“Hacer sonar” emitidas por la app para investigar pitidos sin confundirlos con avisos del firmware.


### V116 · botones de limpieza desbloqueados por estado físico

- Corrige el caso donde **Iniciar limpieza** no hacía nada aunque el E10 estuviera físicamente en **Cargando**.
- Una bandera `mapping_active` residual ya no deshabilita la limpieza cuando el estado real es 0/1/3/4.
- Los botones superior, Inicio/Acciones rápidas y cualquier botón equivalente se reenlazan explícitamente a `App.start_clean` V116.
- El clic se registra en F12 y en el banner **antes** de cualquier lectura de red.
- La limpieza global ya no exige `native_grid`; si hay mapa Xiaomi se protege, pero nunca se usa como condición para permitir START.
- Fallos al aplicar succión/agua se registran y no impiden intentar el arranque.
- Se conserva V115: fallback por modo → start genérico → whole-home y éxito sólo con status físico 5/6/7.


### V115 · inicio global verificado + mapa congelado durante limpieza

- **Iniciar limpieza** ya no toma un ACK MIoT como prueba de éxito: confirma físicamente que el E10 cambió a estado 5/6/7.
- Fallback B112 en tres rutas, sin remapear: acción por modo → start genérico → whole-home.
- El botón muestra **Iniciando…** y luego **Limpiando…**; si ninguna ruta mueve el robot aparece un error visible en vez de fallar en silencio.
- Durante la limpieza global y el retorno, el `native_grid` Xiaomi guardado queda congelado y cualquier mutación inesperada se restaura.
- Se bloquean Mapear/cambiar/eliminar mapa y las actualizaciones live de geometría mientras la limpieza global está activa.
- F12 V115 registra método usado, estados antes/después, respuestas de cada intento, errores y fingerprints del mapa.
- No cambia el decoder ni la geometría V113/V111.


Este archivo resume **hitos importantes**, no cada build interno. Para el detalle de cada publicación consultá [GitHub Releases](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases).

## Unreleased

### V114 · mapa Xiaomi operativo

- Conserva exactamente la geometría final V113/V111; esta versión no modifica decoder, layout ni selección del mapa final.
- Habitaciones, zonas y puntos requieren un `native_grid` Xiaomi final antes de poder ejecutar limpieza dirigida.
- Cada selección se recorta contra las celdas ocupadas reales del grid de 0,20 m.
- Las zonas bloqueadas se restan de la geometría operativa antes de generar órdenes al robot.
- Una forma irregular se divide en rectángulos seguros; nunca se amplía a un rectángulo que incluya superficie exterior al mapa.
- El marco visual final y la conversión física comparten el mismo origen de dock; luego se convierte a raw con `1 raw = 0,10 m`.
- Durante limpieza dirigida se activa un guard en el E10: `arm_new_map`, `build-map` y las rutas `start_mapping_*` quedan bloqueadas por código.
- Mientras una limpieza dirigida está activa no se puede iniciar mapeo, cambiar mapa, crear mapa ni eliminar el mapa activo.
- El `native_grid` final queda congelado durante la limpieza y se restaura automáticamente si cambia, desaparece o un evento externo cambia temporalmente el mapa activo.
- Una habitación local nunca se envía como `room-id` Xiaomi: se convierte exclusivamente en superficie del grid final.\n- Las programaciones que apuntan a zonas usan la misma ruta operativa segura.
- F12 V114 informa selección local, área pedida/limpiable, subzonas, coordenadas raw, comandos completados, hash del mapa y bloqueos de mapeo.
- Conserva V113 retorno sin frenado automático, renderer compatible, panel Habitaciones/Zonas, privacidad de IP y anti-freeze.


### V113 · geometría V111 congelada + retorno seguro

- Conserva exactamente el selector geométrico V111, cuya salida final fue visualmente cercana a Mi Home en la última prueba.
- Se elimina de la versión activa el gate rígido V112 que obligaba a conservar al menos 84% del componente V93.
- Se mantiene la espera de lecturas finales y el filtrado que permitió obtener la planta más fiel observada hasta ahora.
- `_v87_draw_rooms_and_plan(..., transform=None)` conserva el contrato V88/V110 y elimina el TypeError repetitivo del renderer.
- El watchdog de retorno no ejecuta `vacuum.stop()` ni `manual(5)` al vencer 120 s.
- Un retorno prolongado sólo muestra aviso y continúa bajo control del firmware hasta confirmar `status=4`.
- F12 V113 identifica explícitamente que la geometría activa es V111 y registra avisos/progreso del retorno.
- Conserva diagnóstico completo V111, Habitaciones/Zonas V110, privacidad de IP, renderer moderno y anti-freeze.


### V112 · geometría retenida + retorno sin frenado

- El mapa final queda anclado al candidato V93 espacialmente válido en vez de volver a puntuar libremente máscaras mucho más pequeñas.
- Un candidato final debe conservar al menos 84% del componente principal V93; el caso real 265→196 queda explícitamente bloqueado.
- La planta final debe seguir cubriendo la extensión de la trayectoria real en ambos ejes, con un margen físico para el centro del robot.
- Si `cleaning-area 7/23` es 0, la referencia de superficie se deriva de la huella/extensión de la trayectoria y no del área de tarea mostrada por Mi Home.
- Se conserva trayectoria + topología + orientación como criterios de selección, pero una buena cercanía a la polilínea ya no puede ganar a costa de recortar demasiado la planta.
- `_v87_draw_rooms_and_plan(..., transform=None)` restaura el contrato V88/V110 y elimina el TypeError repetitivo del renderer.
- El watchdog de retorno ya no ejecuta `vacuum.stop()` ni `manual(5)` al vencer 120 s.
- Un retorno superior a 120 s pasa a ser sólo **Retorno prolongado**; el firmware mantiene control hasta confirmar `status=4`.
- F12 V112 informa baseline V93, mínimo retenido, celdas finales, retención, candidatos descartados y avisos de retorno prolongado.
- Conserva V111 diagnóstico completo, V110 Habitaciones/Zonas, renderer moderno, privacidad de IP y anti-freeze.


### V111 · área retenida + diagnóstico completo

- Corrige el error de F12 de V110: `_v87_floor_cells` vuelve a respetar el contrato `@classmethod` esperado por V91/V97/V99 y acepta `snapshot=None` sin interpretar el diccionario como `self`.
- El área raw 7/23 del B112 se conserva durante toda la sesión de mapeo y no se pierde al volver/cargar.
- Si el batch `get_properties` devuelve 0 para 7/23 durante una sesión activa/retorno/dock, el driver intenta una lectura directa de la propiedad.
- La app mantiene el máximo raw y el máximo de área observado desde el inicio del mapeo.
- El selector final resuelve una única escala para el raw (×1, ×0,1 o ×0,01) comparándola con la huella física de la trayectoria; todos los candidatos compiten contra el mismo objetivo.
- Se mantiene la puntuación V110 por trayectoria + área + topología.
- Gate de seguridad: si el mejor grid final difiere más de 42% del área física objetivo, no se guarda como mapa definitivo.
- F12 V111 informa raw máximo, área máxima, factor inferido, área estimada por trayectoria, área del grid elegido y error relativo.
- Conserva V110 Habitaciones/Zonas, renderer moderno, privacidad de IP, escala física de presentación y anti-freeze.


### V110 · habitaciones ancladas + escala física

- Cada zona de limpieza y bloqueo tiene un `room_id` obligatorio y pertenece a una habitación.
- Sin habitación activa no se pueden crear zonas; una zona nueva debe quedar dentro de su habitación.
- Cambiar de habitación cambia la lista y los overlays de zonas visibles.
- Borrar una habitación elimina en cascada sus zonas, bloqueos y referencias desde programaciones.
- El lateral derecho se rediseña con selector Habitaciones/Zonas, tarjetas modernas, contadores y selector de habitación activa.
- Debajo del mapa sigue quedando únicamente **Administrar mapas**.
- Se agrega compatibilidad para `_v87_floor_cells(snapshot=None)` y recuperar el diagnóstico completo heredado.
- `cleaning-area` MIoT se interpreta en centésimas de m² y se conserva tanto raw como convertido.
- La selección final del grid combina trayectoria, área física real y topología para penalizar máscaras ralas, huecos y contornos artificiales.
- La vista automática inicial se limita a 72 px/m para mantener una escala visual física más cercana a Mi Home, sin afectar zoom/pan manual.
- Se conservan privacidad de IP, renderer moderno y optimizaciones anti-freeze.


### V109 · mapa físico + panel lateral + diagnóstico seguro

- El mapa final ya no acepta el layout 2bpp sólo por conectividad: compara layout, máscara y orientación global contra la trayectoria física real del E10.
- Prueba reflejos/rotaciones alrededor de la base y puntúa cobertura del recorrido, distancia media, percentil 90, tamaño físico y fragmentación.
- La limpieza de habitaciones y zonas corrige la escala: el mapa local está en metros y el E10 usa 1 raw = 0,10 m.
- El origen de limpieza localizada se repara con la base raw real de V77/V78, evitando guardar el (0,0) normalizado como origen físico.
- La franja inferior del mapa queda exclusivamente para **Administrar mapas**.
- Habitaciones y zonas pasan a un panel derecho con pestañas; permite seleccionar, limpiar, bloquear/desbloquear, crear y eliminar.
- F12 tiene salida de emergencia y ya no puede quedar en blanco si falla una sección heredada.
- Copiar diagnóstico usa la misma ruta protegida.
- La interfaz de conexión muestra sólo **Conectado** y las direcciones IPv4 se redactan del diagnóstico.
- Se conservan el renderer moderno V108, la estrategia final-first V107 y las optimizaciones anti-freeze.


### V108 · renderer moderno obligatorio

- El último pase visual de mapa grande y miniatura borra cualquier dibujo heredado antes de presentar la interfaz.
- Se restauran fondo azul, piso azul, contorno azul, base verde y robot circular.
- El recorrido interno permanece oculto; tampoco pueden quedar visibles la grilla antigua, la base naranja ni elementos/perímetros naranjas.
- Durante un mapeo nuevo, antes de tener mapa Xiaomi final, se muestran sólo fondo moderno + base/robot y un aviso discreto de espera.
- Los mapas guardados antiguos sin grid Xiaomi final vuelven a usar el piso estimado moderno con relleno y contorno, sin recorrido interno.
- Cuando existe grid Xiaomi final, se usa el mismo renderer moderno tanto en el mapa grande como en la miniatura.
- Se conservan íntegramente la estrategia final-first y las optimizaciones anti-freeze de V107.


### V107 · mapa final primero + anti-freeze

- La planta deja de reconstruirse en vivo: durante el mapeo se priorizan pose, base y control del robot.
- No se hace polling/decodificación Cloud de la planta cada pocos segundos; el mapa se captura al finalizar en el dock.
- Al confirmar `status=4`, se hacen 3 lecturas finales Xiaomi y se prefiere un frame actual repetido/estable.
- El mapa final ya no usa la unión histórica `acum[N]`; toma el frame actual del layout/máscara elegido por la coherencia física V93.
- No se rellenan huecos ni se agregan celdas al mapa final; sólo se elimina geometría completamente separada.
- La geometría final se refleja en Y alrededor de la base para igualar la orientación visual observada en Mi Home.
- Render completo limitado a 1,5 s; galería de mapas a 12 s; refresh global de tema/i18n a 15 s; eventos UI en lotes de 4.
- Se eliminan miles de `configure()` redundantes del fondo de canvas.
- Un mapa ya guardado sigue visible al reiniciar; la superficie sólo se oculta al comenzar un mapeo nuevo.


### V106 · densidad 2x2 sin inflar el mapa

- El preview Xiaomi ya no convierte automáticamente cada bloque ambiguo 2×2 en 0,16 m² completos.
- Conserva cuántas de las cuatro subceldas de 0,20 m están realmente ocupadas en cada bloque, dato que es invariante a la permutación `tile2`.
- Usa mediana baja sobre hasta 5 frames recientes para eliminar ocupaciones transitorias sin unión acumulativa.
- Reconstruye un preview de 0,20 m preservando el área observada; las subceldas ambiguas se colocan hacia el núcleo/dock para evitar expandir el borde.
- Mantiene el mapa congelado de V105 durante retorno y dock.
- Si V57 valida el mapa completo, el preview se reemplaza automáticamente por el grid Xiaomi exacto.


### V105 · preview retenido + consenso temporal

- El último mapa Xiaomi preliminar ya no desaparece cuando `mapping_active` pasa a `False` durante el retorno a base.
- El preview queda congelado y visible en `status=3`, `status=4` y tras el cierre local, hasta recibir una geometría mejor o iniciar un mapa nuevo.
- El preview parcial deja de usar una unión acumulativa permanente.
- V105 toma el frame físico actual de V93 y usa consenso por mayoría de hasta 5 hashes recientes.
- Las celdas transitorias deben repetirse en suficientes frames antes de quedar en la planta, reduciendo la inflación de área.
- Se registra `cleaning_area` MIoT 7/23 en F12 para comparar el área física reportada por el E10 con Mi Home.


### V104 · preview Xiaomi independiente del layout

- El mapa parcial ya no queda bloqueado porque el frame actual y el acumulado elijan permutaciones `tile2` diferentes.
- Mientras Xiaomi todavía no tenga un grid V57 válido, cada bloque 2×2 de la rejilla de 0,20 m se resume en una celda física de 0,40 m.
- Esa reducción hace que `tile2-1203`, `tile2-0213` y las demás permutaciones locales produzcan la misma planta preliminar.
- El preview preliminar puede aparecer tras 2 hashes distintos y 25 s, sin esperar las 100 celdas de V103.
- Los saltos fuertes de crecimiento reinician la acumulación coarse.
- Cuando V57 valida el grid completo, la app vuelve automáticamente a la resolución Xiaomi de 0,20 m.


### V103 · geometría Xiaomi con espera de confianza

- La planta parcial deja de aparecer apenas salen los primeros blobs del dock.
- Un preview no validado por V57 exige 4 hashes distintos con el mismo layout/máscara, al menos 60 s de mapeo y 100 celdas antes de mostrarse.
- Si el layout cambia o el área salta bruscamente entre lecturas, la confianza vuelve a cero en vez de agrandar/deformar el plano.
- Durante la espera se conservan base y aspiradora y la UI muestra “validando geometría Xiaomi”.
- Un grid que ya supera V57 puede mostrarse sin demora adicional.
- Inicializa `map_selected_xy` antes de la cadena V88/V101 y elimina el error de renderer detectado en V102.


### V101 · grid Xiaomi realmente dibujado

- Corrige el fallo de renderer que dejaba el canvas vacío aunque V100 ya hubiera aceptado un grid Xiaomi live parcial.
- La causa estaba en el contrato heredado V88/V87: V88 llamaba `_v87_xy(canvas, transform)`, pero V87 definía `_v87_xy(point)`.
- V101 agrega un adaptador dual que soporta ambos usos sin romper el parser de puntos.
- Después de cada render cuenta los objetos `v88_xiaomi_floor`; si hay grid Xiaomi y el canvas queda con 0, fuerza la capa nativa.
- La miniatura activa se refresca inmediatamente con cada frame Xiaomi recibido.
- F12 V101 muestra celdas disponibles, objetos realmente dibujados, hits del adaptador, redraws forzados y errores de renderer.


### V100 · Xiaomi live-first + mapa sin flicker

- La geometría Xiaomi pasa a ser la fuente visual prioritaria durante el mapeo.
- Un grid Xiaomi parcial puede mostrarse antes de superar el gate de mapa completo de V57 si es espacialmente coherente: mínimo 8 celdas, hasta 3 componentes, ratio del componente principal ≥0,82, adyacencia ≥0,75 y base cercana.
- V57 sigue siendo obligatorio para persistir el grid como mapa definitivo; la relajación sólo afecta a la vista en vivo.
- Durante `mapping_active`, V100 usa un **fast-path directo al slot 0 B112** aproximadamente cada 6 s. Ya no espera el ciclo estructurado largo V60 para actualizar la vista.
- El refresco oficial rota una sola acción por ciclo (`10/18` → `10/15` → `10/6`) y conserva la protección de un único worker, evitando volver al consumo alto de CPU/RAM.
- El mapa grande y las miniaturas quedan con fondo fijo `#dfe9f2`; el sistema Claro/Oscuro ya no puede cambiar el fondo de esos canvases, eliminando el titileo blanco/azul.
- Si existe un grid Xiaomi live utilizable, no se vuelve visualmente al fallback estimado.
- El texto visible del instalador se simplifica a **“La instalación está en proceso”**.
- F12 V100 informa si la fuente visual es Xiaomi live parcial o Xiaomi validado, métricas del candidato y contadores de aceptación/rechazo.


### V99 · mapa estable, dark theme e i18n completa

- Durante una sesión nueva no se dibuja ninguna superficie estimada hasta disponer de un grid Xiaomi validado o exploración 2D realmente madura.
- El fallback 2D exige ahora al menos 60 puntos, 1,40 m de extensión principal, 0,90 m lateral, ratio 2D ≥ 0,45 y al menos 7 filas/columnas exploradas.
- El viewport de mapeo parte de 4×4 m centrado en la base y sus límites son **monotónicos**: pueden expandirse, pero nunca encogerse ni cambiar de centro por un frame parcial.
- Una vez validado un grid Xiaomi, V99 lo retiene como fuente visual aunque un frame posterior llegue incompleto; puede actualizarse con otro grid válido, pero no alterna visualmente con el fallback.
- Tema oscuro reescrito sobre la paleta real de la interfaz heredada: páginas, tarjetas, labels, canvas, entries, comboboxes, bordes y diálogos.
- Los botones de acción azules mantienen texto blanco en normal, hover y disabled.
- Localización dinámica para Español / English / Português: los textos que se regeneran al refrescar mapa/estado vuelven a pasar por el traductor.
- “Administrar mapas” muestra **Eliminar** siempre. Si se elimina el último mapa, se borran geometría/rooms/zonas/puntos/rutinas y queda automáticamente un slot vacío válido.
- F12 V99 informa fuente visual, bounds acumulados, contracciones bloqueadas, grid retenido, tema e idioma.


### V98 · tema, idiomas, updater integrado y arranque estable

- Configuración incorpora tema **Claro/Oscuro**, persistente entre reinicios.
- Configuración incorpora idioma **Español / English / Português**, persistente y aplicado a la navegación, controles principales, estado y textos esenciales.
- El actualizador mantiene una interfaz visual durante descarga/verificación y transfiere la instalación a un helper GUI con el mismo tema/idioma.
- El instalador se ejecuta con `/VERYSILENT`, `CREATE_NO_WINDOW` y salida estándar oculta: no aparecen CMD/PowerShell ni ventanas del instalador.
- La ventana principal se construye oculta y se muestra una sola vez con su geometría final; se neutralizan los cuatro restores tardíos de V39 que producían maximizar/minimizar repetidamente.
- README principal en inglés, con documentación de entrada separada para español y portugués.
- El workflow intenta sincronizar topics de descubrimiento del repositorio sin bloquear la release si GitHub no concede permiso de administración.
- Conserva V97: fallback de mapa temprano prudente, viewport 4×4 m antes de geometría 2D y sesión Core Audio **Aspiradora** para Sonar.


### V97 · mapa temprano prudente + Sonar

- El fallback estimado ya no convierte unos pocos puntos casi lineales en una habitación completa.
- Antes de tener geometría 2D madura se dibuja sólo una **huella temprana** del recorrido real, sin cierre de huecos ni relleno interior.
- El fallback completo V91 requiere al menos 24 puntos, 1,00 m de extensión mayor, 0,55 m de extensión menor y ratio 2D ≥ 0,35.
- Mientras la geometría aún es temprana, el viewport mantiene un marco mínimo de **4×4 m alrededor de la base**, evitando que un recorrido de menos de un metro ocupe media pantalla.
- Un grid Xiaomi validado sigue teniendo prioridad inmediata sobre cualquier fallback.
- Para SteelSeries Sonar, la app crea una sesión de audio silenciosa propia y persistente, identifica el PID por varias rutas de Core Audio y fuerza `DisplayName=Aspiradora`.
- F12 V97 muestra `silent_session_started`, sesiones propias detectadas, sesiones renombradas y el último nombre observado.


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
