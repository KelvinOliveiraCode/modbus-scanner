# Como contribuir com o modbuslab

Obrigado pelo interesse. Este guia explica o que o laboratorio espera de uma
contribuicao e como verificar se a mudanca esta correta.

## O que este laboratorio e

Um laboratorio de protocolo Modbus TCP implementado do zero, com medidores de
energia ficticios, scanner de barramento e leitura de consumo pela rede. O
codigo fala portugues: identificadores, docstrings e comentarios estao em
portugues, e o README principal tambem. Mantenha esse padrao.

## Antes de abrir um issue

- **Defeito**: use o formulario "Relato de defeito". Informe o comando exato, a
  versao do pacote, a versao do Python e o sistema operacional. Se faltar
  alguma informacao, escreva `NOT_ENOUGH_INFO` e diga o que falta.
- **Recurso**: use o formulario "Proposta de recurso". Comece pelo problema,
  nao pela solucao.

Nao abra issue em branco: o formulario existe para nao perder informacao.

## Ambiente de desenvolvimento

```bash
git clone https://github.com/KelvinOliveiraCode/modbus-scanner.git
cd modbus-scanner
python -m venv .venv
```

Ative o ambiente e instale o pacote com os extras de desenvolvimento:

```bash
# Linux e macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

O `pyproject.toml` e a fonte unica de verdade das dependencias. O
`requirements.txt` delega para ele.

A versao de desenvolvimento esta fixada em `.python-version`. O CI roda em
Python 3.10 e 3.11, em Linux e Windows.

## Verificacoes

Rode tudo antes de abrir o pull request:

```bash
ruff check .
ruff format --check .
mypy
python -m pytest --cov=modbuslab --cov-report=term-missing
python tools/verificar_aceite.py
```

O que cada uma garante:

| Verificacao | O que prova |
|---|---|
| `ruff check` | Nenhum erro de lint: estilo, imports, nomes ambiguos, erros comuns. |
| `ruff format --check` | O codigo esta no formato que o repositorio exige. |
| `mypy` | Os tipos batem, em modo estrito. |
| `pytest` | A suite passa e a cobertura fica acima de 70%. |
| `verificar_aceite.py` | O fluxo inteiro continua funcionando: subir o lab, varrer o barramento, ler os tres medidores pela rede, achar a sequencia de fase invertida e bater o consumo com os registradores. |

A suite de testes prova que cada funcao funciona. A prova de aceite prova
algo que a suite nao prova sozinha: que o fluxo inteiro ainda entrega. As duas
sao necessarias.

## O CI tambem confere os exemplos

`tools/gerar_exemplos.py` regenera `exemplos/leitura-consumo.txt` a partir da
saida real da CLI. O CI falha se o arquivo commitado nao bater com o
gerado. Se voce mudou a saida da CLI de proposito, regenere e commite:

```bash
python tools/gerar_exemplos.py
git add exemplos/
```

Um exemplo desatualizado ensina o numero errado para quem le.

## Padrao de commits

Commits seguem [Conventional Commits](https://www.conventionalcommits.org/pt-br/):

```
feat: adiciona leitura de registradores de entrada
fix(cli): corrige a coluna de fase na tabela de consumo
docs: explica a diferenca entre holding e input register
refactor(servidor): extrai a montagem da resposta
test(protocolo): cobre o PDU de excecao sem codigo
chore: atualiza as dependencias de desenvolvimento
```

O titulo do pull request segue o mesmo padrao e e conferido pelo CI.

## Pull requests

1. Crie uma branch a partir da `main`.
2. Escreva commits pequenos e atomicos. Um commit faz uma coisa.
3. Abra o pull request usando o template. A secao "Validacao executada" so
   aceita comandos que rodaram de verdade, com o resultado observado.
4. Confira o diff final em busca de segredo, limpeza nao relacionada e
   afirmacao sem lastro.

### O que o revisor vai olhar

- O problema esta descrito, e a mudanca responde a ele.
- O comportamento alterado tem teste.
- A documentacao que o repositorio dono foi atualizada.
- A mudanca preserva o comportamento que nao precisava mudar.

## Mudancas no protocolo

O modulo `protocolo.py` e o formato do fio. Ele nao existe para ser
"enfeite": e a mesma implementacao que o servidor e o cliente usam, como em
qualquer implementacao real do protocolo. Se voce alterar o enquadramento,
altere o guia em `docs/protocolo-modbus-tcp.md` junto, e explique no pull
request por que o novo comportamento e correto.

## Escopo

Este e um laboratorio de estudo. Ele roda em loopback, com dados ficticios e
sem persistencia. Ele nao e um simulador de campo: nao tem autenticacao, nao
tem retencao de dados, nao foi feito para pointedos a medidor real, e o
protocolo Modbus TCP, em si, nao tem seguranca. O guia do protocolo explica
isso em detalhe.

Nao aceitamos PR que troque o laboratorio por um produto. Aceitamos PR que
tornem o laboratorio mais correto, mais bem testado ou mais bem documentado.

## Codigo de conduta

Ao participar, voce concorda com o [Codigo de Conduta](CODE_OF_CONDUCT.md).

## Licenca

Ao contribuir, voce concorda em licenciar sua contribuicao sob a licenca MIT
do projeto. Ver [LICENSE](LICENSE).
