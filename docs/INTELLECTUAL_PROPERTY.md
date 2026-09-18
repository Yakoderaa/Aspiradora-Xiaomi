# Propiedad intelectual y protección del proyecto

> Este documento organiza la estrategia del repositorio. No sustituye el asesoramiento de un abogado o agente de propiedad industrial.

## 1. Qué está protegido hoy

En Argentina, los programas de computación están protegidos por derecho de autor desde su creación. El registro no es obligatorio para que exista protección, pero sirve como evidencia de autoría, titularidad y fecha.

El código y la documentación originales de este repositorio llevan un aviso de copyright en [COPYRIGHT.md](../COPYRIGHT.md).

### Registro recomendado: DNDA

Como el proyecto ya fue publicado en Internet, la vía que mejor encaja hoy es el trámite oficial de **software puesto en conocimiento público** ante la Dirección Nacional del Derecho de Autor (DNDA):

- https://www.argentina.gob.ar/servicio/registrar-un-software-puesto-en-conocimiento-publico

Ese registro puede reforzar la prueba sobre quién es el autor/titular y cuándo existía la obra.

Para completar el trámite formal se requieren datos personales del titular, documentación y pagos; esas acciones deben ser realizadas por el titular a través de los canales oficiales.

## 2. Patente: no es lo mismo que copyright

La Ley argentina de Patentes excluye a los **programas de computación como tales** de la categoría de invención. Sin embargo, las directrices del INPI contemplan que una solución implementada por software puede requerir análisis de patentabilidad si su núcleo tiene **carácter técnico** y resuelve un **problema técnico** con novedad, actividad inventiva y aplicación industrial.

Fuente oficial:
- https://www.argentina.gob.ar/normativa/nacional/norma-206352/texto
- https://www.argentina.gob.ar/normativa/nacional/norma-27289/texto

### Qué parte del proyecto podría merecer una consulta de patentabilidad

No corresponde afirmar que estas ideas sean patentables. Sí puede valer la pena que un profesional evalúe, antes de seguir publicando detalles técnicos novedosos, si alguna implementación concreta del sistema antiatasco, del control autónomo o de una solución técnica de mapeo cumple los requisitos.

**No existe actualmente una declaración de “patent pending” en este repositorio.** No debe utilizarse esa expresión hasta presentar efectivamente una solicitud de patente.

## 3. La publicación en GitHub importa

El repositorio es público. GitHub permite a otros usuarios ver y hacer fork del contenido público dentro de la plataforma.

Eso no elimina el copyright del autor, pero significa que el código ya fue divulgado públicamente. Si una futura estrategia de patente depende de novedad, conviene consultar a un agente de patentes **antes de publicar nuevos detalles técnicos potencialmente patentables**.

Si la protección por patente se vuelve una prioridad, una práctica prudente es desarrollar las nuevas ideas patentables en privado hasta definir la estrategia de presentación.

## 4. Marca

El nombre y/o logotipo del proyecto pueden evaluarse por separado como **marca** ante el INPI. El registro de marca protege el signo distintivo utilizado para identificar productos o servicios, no el código fuente.

Información oficial:
- https://www.argentina.gob.ar/node/36576
- https://www.argentina.gob.ar/inpi/marcas

Antes de solicitar una marca se recomienda buscar disponibilidad y elegir correctamente las clases aplicables.

## 5. Licencias de software

Este repositorio no debe adoptar una licencia propietaria incompatible con las obligaciones de sus dependencias.

Actualmente `python-miio` figura bajo GPL-3.0. Antes de comercializar una versión cerrada, redistribuir binarios bajo términos propietarios o intentar impedir toda redistribución, hay que revisar:

1. qué componentes GPL se distribuyen junto con el ejecutable;
2. si la arquitectura actual crea obligaciones de GPL sobre la obra distribuida;
3. si conviene reemplazar, reimplementar o aislar determinadas dependencias;
4. qué licencia final se aplicará al código original.

Hasta completar esa revisión, el archivo [COPYRIGHT.md](../COPYRIGHT.md) registra autoría sin intentar imponer una licencia contradictoria.

## 6. Qué protege cada herramienta

| Herramienta | Protege principalmente |
| --- | --- |
| Copyright / DNDA | Código, documentación y expresión concreta |
| Patente | Invención técnica que reúna los requisitos legales |
| Marca | Nombre, logotipo y signos distintivos |
| Secreto empresarial | Información mantenida realmente en secreto |
| GitHub privado | Reduce divulgación futura, pero no borra copias ya hechas |
| Seguridad del repositorio | Integridad del código, dependencias y secretos |

## 7. Próximos pasos recomendados para el titular

1. Registrar en DNDA la versión publicada que se quiera dejar documentada.
2. Guardar releases, hashes, commits y documentación técnica como evidencia histórica.
3. Definir un nombre/logo final y buscar disponibilidad de marca.
4. Antes de publicar una innovación técnica nueva del antiatasco o mapeo, consultar a un agente de propiedad industrial.
5. Revisar la estrategia de licencias por la dependencia GPL antes de una explotación comercial cerrada.
6. Mantener secretos, tokens y nuevas ideas sensibles fuera del repositorio público.

## 8. Evidencia técnica

Git conserva una línea temporal útil de autoría técnica: commits, tags, releases y hashes. Esto es complementario, no sustituto, de un registro formal cuando se busca una prueba más sólida.
