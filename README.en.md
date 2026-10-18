
# modbus-scanner

![language: Python](https://img.shields.io/badge/language-Python-blue?logo=python)   ![status: done](https://img.shields.io/badge/status-done-green)   ![license: MIT](https://img.shields.io/badge/license-MIT-blue)

## Summary

Python project developed as a software engineering study. Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

## Problem / why it exists

The project addresses a practical scope and automates a task that, done manually, is repetitive and error-prone. The focus is on turning data or processes into reliable output, with readable and testable code.

## Architecture

The code is organized by responsibility:

- Input: reading a file, API, user input or data capture (depending on the module).
- Processing: pure functions or classes that apply business rules, transformation or analysis over the input data.
- Output: writing a file, printing to terminal, HTTP response or report generation.

When applicable, the application separates the data access layer from the business logic layer, so changing the data source does not require rewriting the rules.

## Technologies

- Python 3.x
- pytest
- pytest-cov
- PyYAML
- -e

- GitHub Actions (CI): workflow(s) in `.github/workflows/`

The repository contains automated tests.

## What it does

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

## How to run

Requirements: Python 3.x installed.

```
# install dependencies (if requirements.txt exists)
pip install -r requirements.txt

# run
python main.py

# run tests
pytest
```

## Project structure

- src/ (9 arquivo(s))
- tests/ (6 arquivo(s))
- tools/ (3 arquivo(s))
- dados/ (2 arquivo(s))
- docs/ (2 arquivo(s))
- .github/ (1 arquivo(s))
- exemplos/ (1 arquivo(s))
- .gitattributes, .gitignore, LICENSE, pyproject.toml, README.en.md, README.md, requirements.txt


## Trade-offs and decisions

- Standard library whenever possible; external dependencies only when the benefit justifies maintenance.
- Executable scripts straight away, no complex build step, to ease reproduction.
- Logic separated from input/output to keep processing functions testable.

## Known limitations

- Limited scope to the described slice; it is not a complete platform.
- Depends on Python 3.x at runtime.


## Tests

```
pytest
```

## License

Distributed under the MIT License. See the `LICENSE` file in this repository.

## Author

Kelvin Oliveira, https://github.com/KelvinOliveiraCode
Portfolio: https://kelvinoliveiracode.github.io/portfolio/
