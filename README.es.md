# Aspiradora Xiaomi

Aplicación de escritorio para Windows orientada al **Xiaomi Robot Vacuum E10 (`xiaomi.vacuum.b112`)**.

[English](README.md) · [Español](README.es.md) · [Português](README.pt-BR.md)

> Proyecto comunitario e independiente; no está afiliado ni respaldado por Xiaomi.

## Funciones principales

- Control local del E10 desde Windows.
- Aspirado normal, detener, volver a base, localizar, succión y agua.
- Estado permanente del robot en la barra superior.
- Mapeo en vivo con navegación tipo CAD.
- Cuatro mapas locales, habitaciones, zonas, puntos y bloqueos. Los mapas se pueden renombrar o eliminar desde el administrador.
- Programaciones y bandeja de sistema.
- Vinculación de cuenta Xiaomi mediante QR.
- Actualización desde la propia interfaz con verificación SHA-256.
- Tema **Claro/Oscuro**.
- Idiomas **Español / English / Português**.
- Diagnóstico F12 detallado.
- Identidad de audio para SteelSeries Sonar con el nombre **Aspiradora**.

## Mapeo

El E10/B112 utiliza un formato distinto al de modelos Xiaomi más nuevos. La app combina telemetría MIoT, estado físico de la base, blobs de Xiaomi Cloud y un grid B112 de 120×120 candidato.

La regla visual es conservadora y Xiaomi-first: un **grid Xiaomi parcial coherente puede dibujarse en vivo aunque todavía no sea un mapa completo**; el validador fuerte sigue siendo obligatorio para guardarlo como definitivo. Si Xiaomi aún no entrega un grid utilizable, no se inventa superficie hasta tener exploración 2D suficiente. El viewport no se achica ni salta entre fotogramas parciales.

Más detalles: [docs/MAPPING.md](docs/MAPPING.md).

## Descargar

**[Última versión para Windows](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases/latest)**

## Reportar problemas

Ayuda mucho incluir versión, captura del mapa, qué hizo físicamente el robot, qué mostraba Mi Home y el bloque F12 correspondiente.

Ver [CONTRIBUTING.md](CONTRIBUTING.md).
