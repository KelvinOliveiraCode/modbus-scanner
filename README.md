![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)

# modbus-scanner

Servidor Modbus TCP simulado do zero, com medidores de energia ficticios e scanner de barramento que le consumo pela rede.

## Problema / Por que existe

Modbus TCP e um protocolo simples, mas exemplos prontos costumam pular os detalhes que fazem a diferenca entre funcionar em teste e funcionar em campo.

Nas primeiras versoes deste projeto, dois defeitos so apareceram quando o codigo foi executado de verdade:

- O primeiro scanner nao varria nada. Recebia a lista de dispositivos e sondava um a um. Isso nao e descoberta, e confirmacao do que alguem ja disse. Um scanner que precisa saber o unit id antes de sondar so serve quando o cadastro ja esta perfeito, exatamente quando nao se precisa dele.
- A deteccao de sequencia de fase era fisicamente impossivel. A primeira implementacao comparava tres magnitudes de tensao. Linhas L1-L2-L3 e L1-L3-L2 tem o mesmo RMS, entao os tres numeros saem iguais, a heuristica dizia "normal" sempre, e o erro de campo mais comum em instalacao trifasica nunca era detectado.

Este projeto implementa o protocolo do zero sobre a biblioteca padrao do Python, com um servidor de lab, um scanner que descobre unit ids sem saber a lista antecipadamente, e leitura de consumo a partir de registradores lidos pela rede.

## O que faz

O pacote `modbuslab` expoe quatro comandos pelo modulo `python -m modbuslab`:

- `servidor` - sobe um servidor Modbus TCP em `127.0.0.1` que atende tres medidores ficticios: monofasico (unit id 1), trifasico (unit id 2) e de demanda (unit id 3).
- `varrer` - varre um intervalo de unit ids, envia uma leitura de um registrador para cada um, e lista quem respondeu, quem devolveu excecao e quem nao respondeu nada.
- `ler` - conecta ao servidor, le todos os registradores de cada medidor pela rede e calcula tensao, corrente, potencia, fator de potencia, energia e sequencia de fase.
- `mapa` - imprime o mapa de registradores carregado de `dados/mapa-de-registros.yaml`.

O consumo e montado a partir de valores lidos pela rede, nunca a partir do objeto do medidor no servidor.

## Stack

- Python 3.10 ou superior
- PyYAML 6.0+ (unica dependencia, apenas para carregar os arquivos de dados YAML)
- Biblioteca padrao do Python para tudo o resto: `socket`, `struct`, `threading`, `argparse`, `dataclasses`, `math`
- Desenvolvimento: pytest e pytest-cov

Nao ha dependencias de transporte, de serial RTU, nem de cliente Modbus de terceiros. O protocolo e implementado do zero.

## Como funciona

### Protocolo

`protocolo.py` implementa o enquadramento Modbus TCP: o cabecalho MBAP de 7 bytes (identificador de transacao, identificador de protocolo, comprimento e unit id) mais o PDU. O campo de comprimento conta os bytes que vem depois dele - unit id mais PDU - entao o quadro tem `6 + comprimento` bytes, e nao `7 + comprimento`. Somar os 7 bytes do MBAP inteiro faz o servidor esperar um byte que nunca chega.

Funcao 3 (holding registers) e funcao 4 (input registers) estao implementadas. Resposta de excecao tem 9 bytes; leitura bem-sucedida tem `9 + 2N` bytes. O cliente le primeiro o MBAP, que declara o comprimento, e so entao le o resto. Assumir um tamanho fixo trava o cliente em toda resposta de excecao.

### Servidor

`servidor.py` escuta em `127.0.0.1`, aceita conexoes persistentes e atende multiplas requisicoes por conexao. Faz despacho por unit id: o MBAP carrega o endereco do dispositivo, entao dois medidores podem ter o registrador 0 com valores diferentes. Acumula bytes de `recv` em buffer ate ter MBAP mais PDU completo, porque TCP pode entregar um quadro em varias chamadas. Unit ids desconhecidos recebem silencio (sem resposta), igual a um device de campo.

### Scanner e cliente

`scanner.py` varre o intervalo de unit ids. Cada id e sondado com uma leitura de um unico registrador (funcao 4, somente leitura, sem efeito colateral). Tres resultados possiveis: dados (existe e responde), excecao (existe alguem, mas naquele endereco nao) ou ausencia (timeout). O scanner falha alto se nenhum device responder, porque "nenhum device" e "sem servidor" sao diagnosticos opostos.

`ClienteModbus` mantem uma conexao persistente aberta para toda a vida do cliente, como um cliente de poll real.

### Registros

`registros.py` carrega o mapa de registradores de `dados/mapa-de-registros.yaml`. Cada registrador tem nome, endereco, tipo (uint16, int16, uint32, int32), unidade e escala. Valor de engenharia e `bruto / escala`. Registradores de 32 bits ocupam dois enderecos, palavra alta primeiro (convencao Modicon). Um medidor que passou de 65535 kWh precisa dos dois enderecos: ler so a palavra alta daria 65536 onde o valor era 91240.

### Consumo

`consumo.py` calcula tensao, corrente, potencia ativa, reativa e aparente, fator de potencia e energia a partir de um dicionario de valores de engenharia. Para medidor trifasico, a tensao e a media das tres fases e a corrente e a soma das correntes de fase. A sequencia de fase e decidida pelo angulo de fase: salto de L1 para L2 de 240 graus indica sequencia positiva, 120 graus indica negativa. Comparar magnitudes de tensao nao pode distinguir as duas sequencias porque o RMS e o mesmo em ambas.

### CLI

`cli.py` expoe os comandos `servidor`, `varrer`, `ler` e `mapa`, com argumentos comuns `--host`, `--porta`, `--timeout`, `--de` e `--ate`.

## Como rodar

Requer Python 3.10 ou superior. Roda em Windows, Linux e macOS, apenas em loopback.

```powershell
# 1. Instalar
git clone https://github.com/kelvinoliveira/modbus-scanner.git
cd modbus-scanner
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Subir o servidor de lab
python -m modbuslab servidor --porta 5020

# 3. Em outro terminal, varrer o barramento
python -m modbuslab varrer --porta 5020 --de 1 --ate 3

# 4. Ler o consumo pela rede
python -m modbuslab ler --porta 5020 --de 1 --ate 3
```

Saida esperada da leitura:

```
 ID  Dispositivo      Tipo                       V       A        W     var     FP       kWh  Fases
---------------------------------------------------------------------------------------------------
  1  medidor-1pn      medidor monofasico     219.4   12.35     2430     890  0.939   18432.0  1
  2  medidor-3pn      medidor trifasico      219.7   54.90    10980    3120  0.962   91240.0  3 (negativa)
  3  medidor-demanda  medidor de demanda     220.3   43.58     9600    4100  0.920  412880.0  1
```

O medidor trifasico reporta sequencia de fase negativa (invertida), que e o erro de campo classico de instalacao trifasica.

Para gravar a leitura em arquivo:

```powershell
python -m modbuslab ler --porta 5020 --saida exemplos/leitura-consumo.txt
```

Para ver o mapa de registradores:

```powershell
python -m modbuslab mapa
```

Para validar:

```powershell
python -m pytest --cov=modbuslab --cov-report=term-missing
python tools/verificar_encoding.py
python tools/verificar_aceite.py
```

O teste de aceitacao sobe o servidor de verdade, varre o barramento, le os tres medidores por TCP e exige que a sequencia de fase invertida apareca e que o consumo bata com os registradores.

## Estrutura do projeto

```
modbus-scanner/
├── src/modbuslab/
│   ├── __init__.py   Exporta a API publica do pacote
│   ├── __main__.py   Permite executar como python -m modbuslab
│   ├── cli.py        Comandos servidor, varrer, ler, mapa
│   ├── consumo.py    Potencia, fator de potencia, kWh, sequencia de fase
│   ├── dispositivos.py  Medidores ficticos e carga dos dados YAML
│   ├── protocolo.py  Enquadramento MBAP + PDU, excecoes, decodificacao
│   ├── registros.py  Mapa de registradores, escala, 32 bits, carga de YAML
│   └── scanner.py    Cliente Modbus TCP e varredura de barramento
├── tests/            Suite de integracao com servidores reais em TCP
├── tools/
│   ├── gerar_exemplos.py       Regenera os exemplos com saida real
│   ├── verificar_aceite.py     Prova de aceite: servidor, varredura, leitura
│   └── verificar_encoding.py   Gate de U+FFFD e ideograma CJK
├── dados/
│   ├── dispositivos.yaml       Os tres medidores e seus valores
│   └── mapa-de-registros.yaml  Endereco, tipo, escala e unidade
├── docs/
│   ├── mapa-de-registros.md    Escala, 32 bits, angulo de fase
│   └── protocolo-modbus-tcp.md Framing, funcao, excecao, ausencia de seguranca
├── exemplos/leitura-consumo.txt  Varredura, leitura e mapa com saida real
├── pyproject.toml              Metadados do pacote, dependencias, configuracao de pytest e cobertura
├── requirements.txt            Dependencias de desenvolvimento
└── LICENSE                     MIT
```

## Trade-offs e decisoes

- **Conexao persistente.** O cliente mantem o socket aberto para toda a vida do cliente. Custa um descritor a mais, mas replica o comportamento de um cliente de poll real e evita reconectar a cada leitura.
- **Varredura com funcao 4.** Input registers e somente leitura, entao a sonda nao tem efeito colateral no dispositivo alvo.
- **Silencio para unit id desconhecido.** O servidor descarta quadros de unit id que nao atende, sem excecao. Isso replica o comportamento de um device de campo e e o que faz a varredura levar tempo: cada id morto custa um timeout completo.
- **Angulo em vez de tensao para sequencia de fase.** Linhas L1-L2-L3 e L1-L3-L2 tem o mesmo RMS. So o angulo de fase distingue as duas sequencias.
- **So leitura (funcoes 3 e 4).** As funcoes de escrita (6 e 16) nao estao implementadas. Uma ferramenta de leitura de consumo nao precisa escrever em medidor, e deixar a escrita ausente faz o servidor responder excecao 1 em vez de aceitar um comando que so o teste usaria.
- **Dados fixos em YAML.** O catalogo de medidores e carregado de `dados/*.yaml`. Trocar as rotas exige editar esses arquivos, nao codigo.
- **Sem memoria persistente.** Cada processo do servidor comeca do zero. Os medidores nao guardam estado entre reinicializacoes.

## Limitacoes conhecidas

- Nao implementa as funcoes de escrita (6 e 16).
- Nao faz parse de frame Modbus serial (RTU), nem TCP/IP ASCII.
- Nao suporta passagem de parametro em bytes, nem agrupamento de devices.
- O catalogo e fixo: trocar as rotas exige mudar `dados/*.yaml`.
- O lab e TCP simples em threads em loopback. Serve para auditoria e teste de protocolo, nao para medir desempenho nem latencia sob carga.
- Os medidores nao tem memoria persistente: cada processo comeca do zero.
- Escuta apenas em `127.0.0.1` por escolha de seguranca: Modbus TCP nao tem autenticacao, cifragem nem integridade.

## Licenca

MIT. Ver [LICENSE](LICENSE).

## Autor

Kelvin Oliveira - kelvinrebelosw@gmail.com
