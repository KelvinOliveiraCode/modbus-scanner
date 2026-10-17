# modbus-scanner

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)

Modbus TCP server simulated from scratch, with fictional energy meters and a bus scanner that reads consumption over the network.

## Problem / Why it exists

Modbus TCP is a simple protocol, but ready-made examples usually skip the details that make the difference between working in a test and working in the field.

In the first versions of this project, two defects only showed up when the code actually ran:

- The first scanner did not scan anything. It received the device list and probed them one by one. That is not discovery, it is confirmation of what someone already said. A scanner that needs to know the unit id before probing only works when the register is already perfect, exactly when you do not need it.
- Phase sequence detection was physically impossible. The first implementation compared three voltage magnitudes. Lines L1-L2-L3 and L1-L3-L2 have the same RMS, so the three numbers come out equal, the heuristic said "normal" always, and the most common field error in three-phase installation was never detected.

This project implements the protocol from scratch over Python's standard library, with a lab server, a scanner that discovers unit ids without knowing the list in advance, and consumption reading from registers read over the network.

## What it does

The `modbuslab` package exposes four commands through `python -m modbuslab`:

- `servidor` - brings up a Modbus TCP server on `127.0.0.1` serving three fictional meters: single-phase (unit id 1), three-phase (unit id 2), and demand (unit id 3).
- `varrer` - scans a range of unit ids, sends a single-register read to each, and lists who responded, who returned an exception, and who did not respond at all.
- `ler` - connects to the server, reads all registers of each meter over the network and computes voltage, current, power, power factor, energy, and phase sequence.
- `mapa` - prints the register map loaded from `dados/mapa-de-registros.yaml`.

Consumption is built from values read over the network, never from the meter object on the server.

## Stack

- Python 3.10 or higher
- PyYAML 6.0+ (only dependency, only to load YAML data files)
- Python standard library for everything else: `socket`, `struct`, `threading`, `argparse`, `dataclasses`, `math`
- Development: pytest and pytest-cov

No transport, serial RTU, or third-party Modbus client dependencies. The protocol is implemented from scratch.

## How it works

### Protocol

`protocolo.py` implements Modbus TCP framing: the 7-byte MBAP header (transaction id, protocol id, length, unit id) plus the PDU. The length field counts the bytes that come after it - unit id plus PDU - so the frame has `6 + length` bytes, not `7 + length`. Summing all 7 MBAP bytes makes the server wait for a byte that never arrives.

Function 3 (holding registers) and function 4 (input registers) are implemented. Exception response is 9 bytes; successful read is `9 + 2N` bytes. The client reads the MBAP first, which declares the length, and only then reads the rest. Assuming a fixed size locks the client on every exception response.

### Server

`servidor.py` listens on `127.0.0.1`, accepts persistent connections, and serves multiple requests per connection. It dispatches by unit id: the MBAP carries the device address, so two meters can have register 0 with different values. It accumulates bytes from `recv` in a buffer until the MBAP plus full PDU is complete, because TCP can deliver one frame across several calls. Unknown unit ids receive silence (no response), like a field device.

### Scanner and client

`scanner.py` scans the unit id range. Each id is probed with a single-register read (function 4, read-only, no side effect). Three results are possible: data (exists and responds), exception (someone is there, but not at that address), or absence (timeout). The scanner fails loudly if no device responds, because "no devices" and "no server" are opposite diagnoses.

`ClienteModbus` keeps a persistent connection open for the whole client lifetime, like a real polling client.

### Registers

`registros.py` loads the register map from `dados/mapa-de-registros.yaml`. Each register has name, address, type (uint16, int16, uint32, int32), unit, and scale. Engineering value is `raw / scale`. 32-bit registers occupy two addresses, high word first (Modicon convention). A meter that passed 65535 kWh needs both addresses: reading only the high word would give 65536 where the value was 91240.

### Consumption

`consumo.py` computes voltage, current, active, reactive and apparent power, power factor, and energy from a dictionary of engineering values. For a three-phase meter, voltage is the average of the three phases and current is the sum of the phase currents. Phase sequence is decided by the phase angle: a 240-degree jump from L1 to L2 indicates positive sequence, 120 degrees indicates negative. Comparing voltage magnitudes cannot distinguish the two sequences because the RMS is the same in both.

### CLI

`cli.py` exposes the commands `servidor`, `varrer`, `ler`, and `mapa`, with common arguments `--host`, `--porta`, `--timeout`, `--de`, and `--ate`.

## How to run

Requires Python 3.10 or higher. Runs on Windows, Linux and macOS, loopback only.

```powershell
# 1. Install
git clone https://github.com/kelvinoliveira/modbus-scanner.git
cd modbus-scanner
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Bring up the lab server
python -m modbuslab servidor --porta 5020

# 3. In another terminal, scan the bus
python -m modbuslab varrer --porta 5020 --de 1 --ate 3

# 4. Read consumption over the network
python -m modbuslab ler --porta 5020 --de 1 --ate 3
```

Expected read output:

```
 ID  Dispositivo      Tipo                       V       A        W     var     FP       kWh  Fases
---------------------------------------------------------------------------------------------------
   1  medidor-1pn      medidor monofasico     219.4   12.35     2430     890  0.939   18432.0  1
   2  medidor-3pn      medidor trifasico      219.7   54.90    10980    3120  0.962   91240.0  3 (negativa)
   3  medidor-demanda  medidor de demanda     220.3   43.58     9600    4100  0.920  412880.0  1
```

The three-phase meter reports negative phase sequence (reversed), which is the classic field installation error.

To save the reading to a file:

```powershell
python -m modbuslab ler --porta 5020 --saida exemplos/leitura-consumo.txt
```

To view the register map:

```powershell
python -m modbuslab mapa
```

To validate:

```powershell
python -m pytest --cov=modbuslab --cov-report=term-missing
python tools/verificar_encoding.py
python tools/verificar_aceite.py
```

The acceptance test brings up the real server, scans the bus, reads the three meters over TCP and requires the reversed phase sequence to appear and consumption to match the registers.

## Project structure

```
modbus-scanner/
├── src/modbuslab/
│   ├── __init__.py   Exports the package public API
│   ├── __main__.py   Allows running as python -m modbuslab
│   ├── cli.py        Commands servidor, varrer, ler, mapa
│   ├── consumo.py    Power, power factor, kWh, phase sequence
│   ├── dispositivos.py  Fictional meters and YAML data loading
│   ├── protocolo.py  MBAP + PDU framing, exceptions, decoding
│   ├── registros.py  Register map, scale, 32 bits, YAML loading
│   └── scanner.py    Modbus TCP client and bus scanning
├── tests/            Integration suite with real TCP servers
├── tools/
│   ├── gerar_exemplos.py       Regenerates examples with real output
│   ├── verificar_aceite.py     Acceptance proof: server, scan, read
│   └── verificar_encoding.py   U+FFFD and CJK ideograph gate
├── dados/
│   ├── dispositivos.yaml       The three meters and their values
│   └── mapa-de-registros.yaml  Address, type, scale and unit
├── docs/
│   ├── mapa-de-registros.md    Scale, 32 bits, phase angle
│   └── protocolo-modbus-tcp.md Framing, function, exception, no security
├── exemplos/leitura-consumo.txt  Scan, read and map with real output
├── pyproject.toml              Package metadata, dependencies, pytest and coverage config
├── requirements.txt            Development dependencies
└── LICENSE                     MIT
```

## Trade-offs and decisions

- **Persistent connection.** The client keeps the socket open for the whole client lifetime. Costs one more descriptor, but replicates real polling client behavior and avoids reconnecting on every read.
- **Scan with function 4.** Input registers are read-only, so the probe has no side effect on the target device.
- **Silence for unknown unit id.** The server drops frames for unit ids it does not serve, without exception. That replicates field device behavior and is what makes scanning take time: each dead id costs a full timeout.
- **Angle instead of voltage for phase sequence.** Lines L1-L2-L3 and L1-L3-L2 have the same RMS. Only the phase angle distinguishes the two sequences.
- **Read only (functions 3 and 4).** Write functions (6 and 16) are not implemented. A consumption reading tool does not need to write to a meter, and leaving write absent makes the server respond exception 1 instead of accepting a command only tests would use.
- **Fixed data in YAML.** The meter catalog is loaded from `dados/*.yaml`. Changing routes means editing those files, not code.
- **No persistent memory.** Each server process starts from zero. Meters do not keep state across restarts.

## Known limitations

- Does not implement write functions (6 and 16).
- Does not parse serial Modbus frame (RTU), nor TCP/IP ASCII.
- Does not support byte-parameter passing or device grouping.
- The catalog is fixed: changing routes means editing `dados/*.yaml`.
- The lab is simple TCP in threads on loopback. Suitable for protocol audit and testing, not for measuring performance or latency under load.
- Meters have no persistent memory: each process starts from zero.
- Listens only on `127.0.0.1` by security choice: Modbus TCP has no authentication, encryption or integrity.

## License

MIT. See [LICENSE](LICENSE).

## Author

Kelvin Oliveira - kelvinrebelosw@gmail.com