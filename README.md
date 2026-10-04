<div align="center">

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/tests-306%20passing-brightgreen?style=flat-square" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-93%25-green-brightgreen?style=flat-square" alt="Coverage">
  <img src="https://img.shields.io/badge/deps-PyYAML%20only-blue?style=flat-square" alt="Deps">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" alt="Windows">
</p>

</div>

# modbus-scanner

Protocolo Modbus TCP implementado do zero, um servidor de lab com medidores de
energia ficticios, e um scanner que descobre dispositivos e le consumo pela
rede.

Modbus TCP implemented from scratch, a lab server with fictional energy meters,
and a scanner that discovers devices and reads consumption over the network.

Sem dependencia alem de PyYAML. O protocolo vive em socket da biblioteca
padrao. Tudo em loopback, tudo offline.

---

## PT-BR

### O que e

Tres coisas que seapoiam:

**O protocolo.** `protocolo.py` implementa o enquadramento Modbus TCP: o
cabecalho MBAP de 7 bytes, o PDU, as funcoes de leitura 3 e 4, e as excecoes.
Servidor e cliente usam o mesmo modulo, que e o que acontece em qualquer
implementacao real do protocolo.

**O alvo.** servidor.py e um servidor que serve tres
medidores ficticios em `127.0.0.1`. Medidor monofasico, medidor trifasico e
medidor de demanda, cada um com seu espaco de registradores, sua escala e seus
valores.

**A ferramenta.** `scanner.py` varre o barramento procurando unit id que
respondem, e `cli.py` le os registradores de cada medidor e calcula o consumo.

O consumo e montado a partir de valores **lidos pela rede**, nunca do objeto do
medidor. A distincao e o ponto do projeto: um consumo calculado a partir do
processo que gerou os numeros nao demonstra nada sobre o protocolo.

### Por que foi feito

Este projeto comecou com dois defeitos que so apareceram quando foram testados
de verdade, e nenhum dos dois aparecia lendo o codigo.

**O scanner nao varria nada.** A primeira versao recebia a lista de dispositivos
e Sondava um a um. Isso nao e descoberta: e confirmacao do que alguem ja disse.
Um scanner que precisa saber o unit id antes de sondar so serve quando o
cadastro ja esta perfeito, que e exatamente quando nao se precisa dele.

**A deteccao de sequencia de fase era fisicamente impossivel.** O primeiro
implementacao decidia sequencia de fase comparando tres magnitudes de tensao. E
impossivel por construcao: as tensoes linha-a-linha tem o mesmo valor RMS nas
duas sequencias, entao os tres numeros sao iguais, a heuristica dizia "normal"
sempre, e o erro de campo mais comum de instalacao trifasica nunca era
detectado. O criterio de aceite do projeto pedia exatamente essa deteccao, e a
implementacao nao podia entrega-la.

A correcao foi usar angulo de fase, que e a unica coisa que distingue as duas
sequencias. O mapa do medidor trifasico expoe agora `angulo_l1`, `angulo_l2` e
`angulo_l3`, e o detector decide pelo salto angular de L1 para L2: 240 graus em
sequencia positiva, 120 em negativa. Detalhamento em
[`docs/mapa-de-registros.md`](docs/mapa-de-registros.md).

### Como rodar

Requer Python 3.10 ou superior. Windows, Linux e macOS.

```powershell
# 1. Instalar
git clone https://github.com/kelvinoliveira/modbus-lab.git
cd modbus-lab
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

A leitura mostra os tres medidores, e o trifasico aparece com a sequencia de
fase invertida:

```
 ID  Dispositivo      Tipo                       V       A        W     var     FP       kWh  Fases
---------------------------------------------------------------------------------------------------
  1  medidor-1pn      medidor monofasico     219.4   12.35     2430     890  0.939   18432.0  1
  2  medidor-3pn      medidor trifasico      219.7   54.90    10980    3120  0.962   91240.0  3 (negativa)
  3  medidor-demanda  medidor de demanda     220.3   43.58     9600    4100  0.920  412880.0  1
```

Para gravar a leitura em arquivo:

```powershell
python -m modbuslab ler --porta 5020 --saida exemplos/leitura-consumo.txt
```

Para ver o mapa de registradores:

```powershell
python -m modbuslab mapa
```

### Validar

```powershell
python -m pytest --cov=modbuslab --cov-report=term-missing
python tools/verificar_encoding.py
python tools/verificar_aceite.py
```

- **306 testes**, **93%** de cobertura, piso configurado em 70%.
- `verificar_encoding.py` falha se algum arquivo tiver caractere de
  substituicao (U+FFFD) ou ideograma CJK.
- `verificar_aceite.py` implementa o criterio de aceite: sobe o servidor, varre o
  barramento, le os tres medidores pela rede e exige que a sequencia de fase
  invertida apareca e que o consumo bata com os registradores.

A suite de integracao sobe servidores de verdade em porta livre e fala por TCP.
Nao ha mock do transporte: um mock so provaria que o codigo chama a funcao que o
mock devolve, e nao que o enquadramento MBAP esta certo.

O CI tambem regenera os exemplos e falha se ficarem desatualizados, entao um
numero errado em documento derruba o build.

### O que aprendi

**O campo comprimento do MBAP conta o que vem depois dele.** O quadro tem
`6 + comprimento` bytes, nao `7 + comprimento`. Somar os 7 do MBAP inteiro faz o
servidor esperar um byte que nunca chega, e o sintoma e um timeout em toda
leitura com o servidor aparentemente vivo. Nenhum teste de unidade pega isso: o
erro so existe entre dois processos.

**Resposta de excecao tem 9 bytes, leitura tem `9 + 2N`.** O cliente que assume
um tamanho fixo trava em toda recusa. A saida correta e ler o MBAP primeiro,
porque ele ja declara o comprimento.

**recv devolve o que chegou, nao o quadro.** Doze bytes podem chegar em duas
chamadas. Servidor que interpreta o que tem no buffer, sem acumular, funciona
em teste e falha em campo, porque segmentacao de TCP nao respeita o seu
`sendall`.

**Energia acumulada nao cabe em 16 bits.** Um medidor que passou de 65535 kWh
precisa de dois enderecos, e cada palavra ocupa o seu endereco proprio. Ler so a
palavra alta dava 65536 onde o valor era 91240, e ler a palavra baixa como
registrador separado dava zero. O bug era invisivel no medidor de duas fases e
aparece no de tres.

**Device de campo descarta unit id desconhecido em silencio.** Responder excecao
2 para todo unit id vazio transformaria a varredura em algo instantaneo e sem
informacao. E o silencio, com o timeout do cliente, que faz a varredura
durar.

**Um scanner que devolve lista vazia quando o servidor esta fora do ar mente.**
"nenhum dispositivo" e "nenhum servidor" sao diagnosticos opostos. O scanner
falha alto nos dois casos, e o teste garante.

### Limitacoes

- Nao implementa as funcoes de escrita (6 e 16). Uma ferramenta de leitura de
  consumo nao precisa escrever em medidor.
- Nao faz parse de frame Modbus serial (RTU), nem TCP/IP ASCII.
- Nao suporta passagem de parametro em bytes, nem agrupamento de devices.
- O catalogo e fixo: trocar as rotas exige mudar `dados/*.yaml`.
- O lab e TCP simples em threads. Serve para auditoria, nao para medir
  desempenho nem latencia sob carga.
- Os medidores nao tem memoria persistente: cada processo comeca do zero.

### Licenca

MIT. Ver [LICENSE](LICENSE).

---

## EN

### What it is

Three things leaning on each other:

**The protocol.** `protocolo.py` implements Modbus TCP framing: the 7-byte MBAP
header, the PDU, read functions 3 and 4, and exceptions. Server and client share
that module, the way any real protocol implementation does.

**The target.** `servidor.py` is a server serving three fictional meters on
`127.0.0.1`: a single-phase meter, a three-phase meter and a demand meter, each
with its own register space, scaling and values.

**The tool.** `scanner.py` sweeps the bus for answering unit ids, and `cli.py`
reads each meter's registers and computes consumption.

Consumption is built from values read **over the network**, never from the meter
object. That distinction is the point of the project: consumption computed from
the process that generated the numbers demonstrates nothing about the protocol.

### Why it was built

This project started with two defects that only showed up under real testing,
and neither was visible by reading the code.

**The scanner did not scan.** The first version took the device list and probed
it one by one. That is not discovery, it is confirmation of what someone already
said. A scanner that needs the unit id before it probes is only useful when the
registry is already perfect, which is exactly when you do not need it.

**Phase-sequence detection was physically impossible.** The first implementation
decided the phase sequence by comparing three voltage magnitudes. That is
impossible by construction: line-to-line voltages have the same RMS value in
both sequences, so the three numbers come out equal, the heuristic says "normal"
every time, and the most common field error in three-phase installation is never
detected. The acceptance criterion asked for exactly that detection, and the
implementation could not deliver it.

The fix was to use phase angle, the only thing that distinguishes the two
sequences. The three-phase meter's map now exposes `angulo_l1`, `angulo_l2` and
`angulo_l3`, and the detector decides on the angular step from L1 to L2: 240
degrees for positive sequence, 120 for negative. Details in
[`docs/mapa-de-registros.md`](docs/mapa-de-registros.md) (Portuguese).

### How to run

Requires Python 3.10 or newer. Windows, Linux and macOS.

```powershell
# 1. Install
git clone https://github.com/kelvinoliveira/modbus-lab.git
cd modbus-lab
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Start the lab server
python -m modbuslab servidor --porta 5020

# 3. In another terminal, sweep the bus
python -m modbuslab varrer --porta 5020 --de 1 --ate 3

# 4. Read consumption over the network
python -m modbuslab ler --porta 5020 --de 1 --ate 3
```

The read shows all three meters, and the three-phase one reports an inverted
phase sequence:

```
 ID  Dispositivo      Tipo                       V       A        W     var     FP       kWh  Fases
---------------------------------------------------------------------------------------------------
  1  medidor-1pn      medidor monofasico     219.4   12.35     2430     890  0.939   18432.0  1
  2  medidor-3pn      medidor trifasico      219.7   54.90    10980    3120  0.962   91240.0  3 (negativa)
  3  medidor-demanda  medidor de demanda     220.3   43.58     9600    4100  0.920  412880.0  1
```

To write the reading to a file:

```powershell
python -m modbuslab ler --porta 5020 --saida exemplos/leitura-consumo.txt
```

To print the register map:

```powershell
python -m modbuslab mapa
```

### Validate

```powershell
python -m pytest --cov=modbuslab --cov-report=term-missing
python tools/verificar_encoding.py
python tools/verificar_aceite.py
```

- **306 tests**, **93%** coverage, floor configured at 70%.
- `verificar_encoding.py` fails if any file holds a replacement character
  (U+FFFD) or a CJK ideograph.
- `verificar_aceite.py` implements the acceptance criterion: it starts the
  server, sweeps the bus, reads the three meters over the network and requires
  the inverted phase sequence to appear and consumption to match the registers.

The integration suite starts real servers on free ports and talks over TCP. The
transport is not mocked, because a mock only proves the code calls the function
the mock returns, not that the MBAP framing is right.

CI also regenerates the examples and fails if they go stale, so a wrong number in
a document breaks the build.

### What I learned

**The MBAP length field counts what comes after it.** The frame is
`6 + length` bytes, not `7 + length`. Adding the full 7-byte MBAP makes the
server wait for a byte that never arrives, and the symptom is a timeout on every
read with the server apparently alive. No unit test catches it: the bug only
exists between two processes.

**An exception response is 9 bytes; a read is `9 + 2N`.** A client that assumes a
fixed size hangs on every refusal. Reading the MBAP first is the fix, because it
already declares the length.

**recv returns what arrived, not the frame.** Twelve bytes can arrive in two
calls. A server that parses the buffer without accumulating works in a test and
fails in the field, because TCP segmentation does not respect your `sendall`.

**Accumulated energy does not fit in 16 bits.** A meter past 65535 kWh needs two
addresses, and each word occupies its own address. Reading only the high word gave
65536 where the value was 91240, and reading the low word as a separate register
gave zero. The bug was invisible on the two-phase meter and shows on the
three-phase one.

**A field device silently drops an unknown unit id.** Answering exception 2 to
every unknown unit id would make the sweep instant and pointless. It is the
silence, plus the client timeout, that makes the sweep take time.

**A scanner returning an empty list when the server is down lies.** "no devices"
and "no server" are opposite diagnoses. The scanner fails loudly on both, and a
test holds it there.

### Limitations

- Write functions (6 and 16) are not implemented. A consumption-reading tool has
  no reason to write to a meter.
- No Modbus serial (RTU) framing, no TCP/IP ASCII.
- No parameter passing in bytes, no device grouping.
- The catalogue is fixed: changing the routes means editing `dados/*.yaml`.
- The lab is plain TCP with threads. It is for auditing, not for measuring
  throughput or latency under load.
- Meters have no persistent memory: each process starts from zero.

### License

MIT. See [LICENSE](LICENSE).

---

## Estrutura / Structure

```
modbus-lab/
├── src/modbuslab/
│   ├── protocolo.py     Enquadramento MBAP + PDU, excecoes, decodificacao
│   ├── servidor.py      Servidor TCP: dispatch por unit id, conexao persistente
│   ├── scanner.py       Cliente Modbus TCP e varredura de barramento
│   ├── registros.py     Mapa de registradores, escala, 32 bits, carga de YAML
│   ├── dispositivos.py  Medidores ficticios e carga dos dados
│   ├── consumo.py       Fator de potencia, potencia, kWh, sequencia de fase
│   └── cli.py           Comandos servidor, varrer, ler, mapa
├── tests/               306 testes, 93% de cobertura
├── tools/
│   ├── verificar_encoding.py   Gate de U+FFFD e ideograma CJK
│   ├── verificar_aceite.py     Prova de aceite do criterio de aceitacao
│   └── gerar_exemplos.py       Regera os exemplos com saida real
├── dados/
│   ├── mapa-de-registros.yaml  Endereco, tipo, escala e unidade
│   └── dispositivos.yaml       Os tres medidores e seus valores
├── docs/
│   ├── protocolo-modbus-tcp.md Framing, funcao, excecao, ausencia de seguranca
│   └── mapa-de-registros.md    Escala, 32 bits, angulo de fase
├── exemplos/leitura-consumo.txt  Varredura, leitura e mapa com saida real
└── .github/workflows/ci.yml      Windows, com gate de cobertura e de aceite
```

## Comandos / Commands

| Comando | O que faz |
| --- | --- |
| `modbuslab servidor` | Sobe o servidor de lab em 127.0.0.1 |
| `modbuslab varrer` | Varre unit ids e lista quem responde |
| `modbuslab ler` | Le os registradores pela rede e calcula o consumo |
| `modbuslab mapa` | Mostra o mapa de registradores |

Argumentos comuns a `varrer` e `ler`: `--host`, `--porta`, `--timeout`, `--de`
(primeiro unit id) e `--ate` (ultimo). `ler` aceita ainda `--saida` para gravar
a leitura.