# Changelog

Todas as mudancas relevantes do modbuslab sao registradas neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
o versionamento segue o [SemVer](https://semver.org/lang/pt-BR/).

## [Nao publicado]

### Adicionado

- Linter, formatador e checagem de tipos: `ruff` (lint e formato) e `mypy` em
  modo estrito, com configuracao em `pyproject.toml`.
- Etapa de qualidade no CI com encoding, `ruff check`, `ruff format --check` e
  `mypy`.
- A suite passa a rodar em `ubuntu-latest` e `windows-latest`, com Python 3.10
  (o minimo declarado) e 3.11.
- Templates de issue (defeito e recurso) e de pull request.
- Checagem de Conventional Commits no titulo do pull request.
- `CONTRIBUTING.md`, `SECURITY.md` e `CODE_OF_CONDUCT.md`.
- `.editorconfig` e `.python-version`.
- `ServidorModbus.aguardar_parada(timeout)`, que substitui o acesso direto ao
  evento interno por parte da CLI.
- `tests/test_api.py`, que fixa o contrato do `__all__` do pacote.

### Mudado

- Dependencias centralizadas no `pyproject.toml`. O `requirements.txt` delega
  para o pyproject com `-e .[dev]` em vez de repetir a lista.
- As actions do GitHub Actions passam a ser referenciadas por SHA, com a
  versao no comentario.
- O workflow declara `permissions: contents: read` e `concurrency` com
  cancelamento.
- `Registrador.engenharia()` aceita `Sequence[int]`, e nao so `list[int]`, que
  e o tipo que a leitura pela rede realmente entrega.

### Corrigido

- `from modbuslab import *` levantava `AttributeError`. O `__all__` listava
  `descrever_excecao`, mas a funcao se chama `descricao_excecao`.
- A CLI criava um `ScannerModbus` no comando `ler` e nunca o usava.
- `ler_dispositivo` atribuia `mapa.tamanho` a uma variavel que nunca era lida.
- Imports sem uso: `typing.Any` em `dispositivos.py`, `FC_READ_HOLDING` e
  `FC_READ_INPUT` em `servidor.py`.
- `int(round(...))` era redundante em `Registrador.brutos()`.
- Os README foram reescritos. Os anteriores descreviam outro projeto, com
  comandos que nao existiam e uma tabela de capacidades sem relacao com o
  laboratorio.

### Removido

- Os aliases `ServidorModbus.start` e `ServidorModbus.stop`, que nao tinham
  consumidor.
- O import de `carregar_mapa` dentro de `carregar_ambiente`, sem justificativa
  de ciclo de importacao.

## [1.0.0]

### Adicionado

- Primeira versao: protocolo Modbus TCP implementado do zero, servidor de
  laboratorio com tres medidores ficticios, scanner de barramento, leitura de
  consumo pela rede e calculo eletrico.
- Suite de testes com 306 casos e cobertura acima de 70%.
- Prova de aceite em `tools/verificar_aceite.py`.
- Gerador de exemplos em `tools/gerar_exemplos.py`.
- Guia do protocolo em `docs/protocolo-modbus-tcp.md` e mapa de registradores
  em `docs/mapa-de-registros.md`.
