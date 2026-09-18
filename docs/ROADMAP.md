# Roadmap

Este roadmap describe dirección, no fechas prometidas. Las prioridades cambian según lo que revele el firmware real del E10.

## Fase actual — Windows + B112

Objetivo: convertir la implementación de Windows en una referencia fiable del protocolo del E10.

- [x] Control local básico.
- [x] Estado, batería, consumibles y regreso a base.
- [x] Instalador Windows.
- [x] Actualizaciones desde GitHub Releases.
- [x] Diagnóstico MIoT específico del B112.
- [ ] Mapeo propio completamente estable.
- [ ] Mapa fresco reproducible después de cada recorrido.
- [ ] Transición automática de todas las fases sin intervención.
- [ ] Antiatasco validado en escenarios reales.
- [ ] Limpieza por habitaciones/zonas basada en mapa estable.
- [ ] Consolidación de módulos de investigación históricos.

## Fase siguiente — motor estable

Una vez que el E10 esté bien comprendido:

- separar protocolo, almacenamiento y UI;
- reducir dependencias entre generaciones `vXX`;
- crear una API interna clara y testeable;
- documentar comandos y quirks del B112;
- ampliar simuladores/fixtures de protocolo;
- mejorar recuperación ante desconexiones.

## Experiencia Windows final

Después de estabilizar el núcleo:

- interfaz más pulida y consistente;
- mapa interactivo fiable;
- automatizaciones y programación;
- perfiles de limpieza;
- diagnóstico simplificado para usuarios;
- logs técnicos exportables;
- actualización más transparente.

## Android e iOS

La intención es evaluar aplicaciones móviles una vez estabilizado el motor.

Una opción especialmente atractiva es una UI compartida en **Flutter**, con módulos nativos para las partes de red/segundo plano que lo requieran.

### Android

Android ofrece bastante libertad para comunicación LAN y servicios durante una limpieza, por lo que es el candidato móvil más directo.

### iOS

iOS también es viable, pero exige respetar permisos de red local y restricciones más fuertes de ejecución en segundo plano. El antiatasco y la monitorización continua deberán diseñarse específicamente para esas reglas.

## Sincronización futura

Una arquitectura posterior podría permitir compartir entre PC y teléfono:

- nombres de habitaciones;
- zonas;
- preferencias de limpieza;
- configuraciones;
- historial local.

La prioridad seguirá siendo que el control del robot pueda funcionar localmente siempre que el protocolo lo permita.
