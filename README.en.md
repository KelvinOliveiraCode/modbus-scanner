# modbus-scanner

[![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://www.python.org/)   ![status: done](https://img.shields.io/badge/status-done-green)   ![license: MIT](https://img.shields.io/badge/license-MIT-blue)

## Summary

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores
## Problem / Why it exists

The project addresses a practical scope and automates a task that, done manually, is repetitive and error-prone. The focus is on turning data or processes into reliable output, with readable, testable, and extensible code.
## Architecture

The code is organized by responsibility into 0 main classes:
## What it does

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores
## How to run

Requirements: Python 3.x installed.

```bash
# install dependencies (if requirements.txt exists)
# no requirements.txt detected
```

```bash
# run
python main.py
```

```bash
# run tests
pytest
```
## Project Structure (Key Classes)


## Trade-offs and Technical Decisions

- Standard library whenever possible; external dependencies only when the benefit justifies maintenance.
- Linear, modular pipeline: each step (EDA, preprocessing, balancing, modeling, evaluation) is an isolated function, easing tests and substitution.
- Optional SMOTE with fallback to `class_weight="balanced"` when `imbalanced-learn` is not installed.
- `RobustScaler` applied only to `Amount` and `Time`; anonymized features (V1-V28) already normalized in the original dataset.
- Model selection by weighted score: Recall(40%) + F1(30%) + Precision(20%) + Accuracy(10%) ,  prioritizes fraud detection (recall) without ignoring precision.
- Artifacts saved via `joblib`: model, scaler, and full results for reproducibility.
## Known Limitations

- Limited to the fraud detection pipeline scope; not a full ML platform.
- Depends on Python 3.x and libraries listed in `requirements.txt`.
- SMOTE only available if `imbalanced-learn` is installed; otherwise falls back to `class_weight`.
- Fixed dataset (TensorFlow creditcard.csv); no ingestion pipeline for new data.
- Models trained on CPU; no GPU/TPU support configured.
## Tests

```bash
pytest
```
No automated tests detected in scan.
## License

Distributed under the MIT License. See the `LICENSE` file in this repository.
## Author

Kelvin Oliveira ,  https://github.com/KelvinOliveiraCode
Portfolio: https://kelvinoliveiracode.github.io/portfolio/
