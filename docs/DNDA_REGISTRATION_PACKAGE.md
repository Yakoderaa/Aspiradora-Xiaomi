# Expediente base para registro DNDA

Este documento reúne información técnica para preparar el trámite argentino de **registro de software puesto en conocimiento público**.

Página oficial del trámite:
https://www.argentina.gob.ar/servicio/registrar-un-software-puesto-en-conocimiento-publico

> El titular debe revisar la información, completar sus datos legales, realizar los pagos y presentar el trámite mediante los canales oficiales. Este archivo no es un certificado ni una solicitud presentada.

## Identificación sugerida de la obra

**Título de la obra:** Aspiradora Xiaomi  
**Tipo:** Programa de computación / software de escritorio  
**Plataforma actual:** Windows 10/11 x64  
**Lenguaje principal:** Python  
**Modelo objetivo:** Xiaomi Robot Vacuum E10 · `xiaomi.vacuum.b112`  
**Repositorio público:** https://github.com/Yakoderaa/Aspiradora-Xiaomi  
**Primera publicación del repositorio:** 16/09/2026  
**Snapshot sugerido para un primer registro:** Release V68 · `v0.1.295`  
**Commit de esa release:** `3756ab9eb82dc91adbdd56667a5b884946d5fb01`

## Datos personales que debe completar el titular

- Nombre y apellido legal:
- DNI:
- CUIL/CUIT:
- Nacionalidad:
- Estado civil:
- Domicilio:
- Correo:
- Teléfono:
- Porcentaje de titularidad:
- Carácter: autor / titular / coordinador / otro:

No publiques estos datos completados en GitHub. Usá una copia local de este documento para el trámite.

## Descripción breve sugerida

> Aplicación de escritorio para Windows destinada al control y supervisión de una Xiaomi Robot Vacuum E10 (modelo MIoT xiaomi.vacuum.b112). El software implementa comunicación local mediante protocolos miIO/MIoT, interfaz de control, monitorización de estado, automatización, actualización de software y un subsistema experimental de mapeo y diagnóstico específico del dispositivo. La obra incluye código propio de interfaz, orquestación, seguridad, persistencia, diagnóstico, control del proceso de mapeo y mecanismos de actualización, utilizando además bibliotecas de terceros identificadas por separado.

Revisá esta descripción antes de presentarla para asegurarte de que corresponda exactamente al snapshot registrado.

## Objetivo y propósito

- controlar el robot desde una PC;
- exponer estados y controles de limpieza;
- automatizar secuencias de operación;
- investigar y reconstruir capacidades de mapeo del B112;
- implementar diagnósticos seguros;
- distribuir actualizaciones verificadas.

## Arquitectura

Ver:
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [MAPPING.md](MAPPING.md)
- [SECURITY_MODEL.md](SECURITY_MODEL.md)

La DNDA admite documentación técnica complementaria para software publicado. Conservá una copia de estos documentos correspondiente al mismo snapshot del código que registres.

## Dependencias y material de terceros

La obra utiliza componentes de terceros. Deben distinguirse del código propio.

Entre ellos:

- `python-miio` — GPL-3.0;
- `micloud`;
- `requests`;
- `Pillow`;
- `pystray`;
- `pycryptodome`;
- `protobuf`;
- parsers de mapas Xiaomi/IJAI.

Ver [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) y `requirements.txt`.

## Material recomendado para conservar localmente

Para cada registro/snapshot guardá en un directorio que **no se suba con datos personales**:

1. ZIP/TAR del tag registrado.
2. Hash SHA-256 del archivo.
3. Copia de `requirements.txt`.
4. Copia de `THIRD_PARTY_NOTICES.md`.
5. Arquitectura y descripción de la versión.
6. URL y fecha de publicación.
7. Release/tag y commit exactos.
8. Comprobante y número de expediente de DNDA cuando exista.

## Código fuente

La normativa argentina admite acompañar información técnica y contempla que el código fuente de software publicado pueda presentarse cifrado/encriptado en determinadas condiciones, quedando el titular responsable de proveer las herramientas necesarias si una autoridad legitimada requiere descifrarlo.

No uses esta posibilidad sin leer las instrucciones vigentes del trámite al momento de presentarlo.

## Verificación antes de presentar

- [ ] Elegí exactamente qué versión quiero registrar.
- [ ] Congelé el tag/commit.
- [ ] Descargué una copia íntegra del código.
- [ ] Separé claramente dependencias de terceros.
- [ ] Revisé que no haya secretos en el material.
- [ ] Completé mis datos legales en una copia local.
- [ ] Revisé aranceles y requisitos vigentes en Argentina.gob.ar.
- [ ] Guardé comprobantes de pago.
- [ ] Guardé el número de expediente.
- [ ] No publiqué en GitHub la copia que contiene mis datos personales.

## Después del registro

Añadí el número de expediente/certificado a tus registros privados. Sólo publicalo en el repositorio si querés hacerlo y si no contiene información que prefieras mantener privada.
