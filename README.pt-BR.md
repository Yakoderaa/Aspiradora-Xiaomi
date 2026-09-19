# Aspiradora Xiaomi

Aplicativo desktop para Windows focado no **Xiaomi Robot Vacuum E10 (`xiaomi.vacuum.b112`)**.

[English](README.md) · [Español](README.es.md) · [Português](README.pt-BR.md)

> Projeto comunitário independente; não é afiliado nem endossado pela Xiaomi.

## Principais recursos

- Controle local do E10 no Windows.
- Iniciar limpeza, parar, voltar à base, localizar, sucção e água.
- Estado do robô sempre visível na barra superior.
- Mapa ao vivo com navegação semelhante a CAD.
- Quatro mapas locais, cômodos, zonas, pontos e bloqueios.
- Agendamento e integração com a bandeja do sistema.
- Vinculação da conta Xiaomi por QR.
- Atualização pela própria interface com verificação SHA-256.
- Tema **Claro/Escuro**.
- Idiomas **Español / English / Português**.
- Diagnóstico F12 detalhado.
- Identidade de áudio para SteelSeries Sonar com o nome **Aspiradora**.

## Mapeamento

O E10/B112 usa um formato diferente de modelos Xiaomi mais novos. O aplicativo combina telemetria MIoT, estado físico da base, blobs do Xiaomi Cloud e um grid B112 candidato de 120×120.

A visualização é conservadora: enquanto o movimento for quase linear, somente a área realmente observada é exibida. O aplicativo não preenche um cômodo inteiro antes de existir exploração 2D suficiente. Um grid Xiaomi validado sempre tem prioridade.

Mais detalhes: [docs/MAPPING.md](docs/MAPPING.md).

## Download

**[Última versão para Windows](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases/latest)**

## Relatar problemas

Inclua a versão, uma captura do mapa, o que o robô fez fisicamente, o que o Mi Home mostrou e o bloco F12 correspondente.

Consulte [CONTRIBUTING.md](CONTRIBUTING.md).
