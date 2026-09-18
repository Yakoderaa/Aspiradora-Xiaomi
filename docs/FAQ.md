# Preguntas frecuentes

## ¿La PC puede estar por Ethernet y el E10 por Wi‑Fi?

Sí. Ambos dispositivos sólo necesitan poder comunicarse dentro de la misma red local. No importa que utilicen medios distintos.

## ¿Reemplaza completamente a Mi Home?

Todavía no. El objetivo a largo plazo es cubrir el uso cotidiano del E10 con una experiencia más completa, pero algunas funciones siguen dependiendo de servicios Xiaomi y el mapeo propio continúa en desarrollo.

## ¿El mapa ya es estable?

No. El mapeo debe considerarse experimental hasta que el proyecto pueda reproducir de forma consistente creación, recuperación, persistencia y uso del mapa después de recorridos completos.

## ¿Por qué hay tantos módulos `vXX`?

El proyecto está atravesando una fase de investigación rápida sobre un firmware real. Las capas incrementales permiten conservar regresiones y comparar comportamientos sin borrar evidencia de versiones anteriores. Cuando el protocolo quede estable, una prioridad será consolidar esa arquitectura.

## ¿Por qué Python?

Porque facilita iterar sobre MIoT, aprovechar `python-miio`, parsers comunitarios y crear diagnósticos rápidamente. Es una buena elección durante la etapa de descubrimiento del protocolo.

## ¿Habrá una versión en C#?

Es una posibilidad para una futura experiencia Windows más nativa, pero no es una prioridad mientras el comportamiento del E10 todavía se está estabilizando.

## ¿Habrá Android e iOS?

Es parte del roadmap. Primero se busca estabilizar el motor del E10. Después se evaluará separar la lógica de comunicación de la interfaz y construir clientes móviles.

## ¿Funcionará con otros robots Xiaomi?

No se debe asumir. El proyecto está diseñado y probado alrededor de `xiaomi.vacuum.b112`. Otros modelos pueden compartir partes del protocolo pero tener propiedades, acciones y formatos de mapa diferentes.

## ¿Por qué Windows muestra SmartScreen o un antivirus puede advertir?

Los builds públicos actuales no cuentan con un certificado comercial de firma de código. Windows puede mostrar advertencias de reputación aunque el archivo haya sido generado por GitHub Actions. Cada release publica un SHA-256 para verificar el instalador.

## ¿Dónde descargo la aplicación?

Sólo desde [GitHub Releases](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases/latest).

## ¿Qué debo adjuntar a un bug?

Versión, Windows, pasos para reproducir, comportamiento esperado/real y, cuando sea relevante, el diagnóstico F12 saneado.

Nunca publiques tokens, contraseñas, cookies o URLs firmadas completas.
