# modbus-scanner

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)   ![status: concluido](https://img.shields.io/badge/status-concluido-green)   ![licenca: MIT](https://img.shields.io/badge/licenca-MIT-blue)

## Resumo

Projeto em Python desenvolvido como estudo de engenharia de software. Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

## Problema / por que existe

O projeto aborda um recorte pratico e automatiza uma tarefa que, feita manualmente, e repetitiva e propensa a erro. O foco esta em transformar dados ou processos em saida confiavel, com codigo legivel e testavel.

## Arquitetura

O codigo esta organizado por responsabilidade:

- Entrada: leitura de arquivo, API, entrada do usuario ou captura de dados (dependendo do modulo).
- Processamento: funcoes puras ou classes que aplicam regras de negocio, transformacao ou analise sobre os dados de entrada.
- Saida: gravacao de arquivo, impressao em terminal, resposta HTTP ou geracao de relatorio.

Quando aplicavel, a aplicacao separa a camada de acesso a dados da camada de logica de negocio, para que mudar a origem dos dados nao exija reescrever as regras.

## Tecnologias

- Python 3.x
- pytest
- pytest-cov
- PyYAML
- -e

- GitHub Actions (CI): workflow(s) em `.github/workflows/`

O repositorio contem testes automatizados.

## O que faz

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

## Como rodar

Requisitos: Python 3.x instalado.

```
# instalar dependencias (se houver requirements.txt)
pip install -r requirements.txt

# executar
python main.py

# executar testes
pytest
```

## Estrutura do projeto

- src/ (9 arquivo(s))
- tests/ (6 arquivo(s))
- tools/ (3 arquivo(s))
- dados/ (2 arquivo(s))
- docs/ (2 arquivo(s))
- .github/ (1 arquivo(s))
- exemplos/ (1 arquivo(s))
- .gitattributes, .gitignore, LICENSE, pyproject.toml, README.en.md, README.md, requirements.txt


## Trade-offs e decisões

- Biblioteca padrao sempre que possivel, dependencias externas so quando o ganho justifica a manutencao.
- Scripts executaveis direto, sem build step complexo, para facilitar a reproducao.
- Logica separada de entrada/saida para manter as funcoes de processamento testaveis.

## Limitações conhecidas

- Escopo limitado ao recorte descrito; nao e uma plataforma completa.
- Depende de Python 3.x no ambiente de execucao.


## Testes

```
pytest
```

## Licença

Distribuído sob a licenca MIT. Consulte o arquivo `LICENSE` do repositorio.

## Autor

Kelvin Oliveira, https://github.com/KelvinOliveiraCode
Portfolio: https://kelvinoliveiracode.github.io/portfolio/
