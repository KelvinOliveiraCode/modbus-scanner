# modbus-scanner

<div align="center">

**English** · [Português (Brasil)](README.md)

</div>

[![Python 3](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikit-learn)](https://scikit-learn.org/) [![pandas](https://img.shields.io/badge/pandas-150458?style=flat-square&logo=pandas)](https://pandas.pydata.org/) [![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest)](https://docs.pytest.org/) [![MIT License](https://img.shields.io/badge/License-MIT-f4c430?style=flat-square)](LICENSE)

### Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

---

## What it is

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

---

## Quick Start

```bash
# Clone and enter
git clone https://github.com/KelvinOliveiraCode/<repo>.git
cd <repo>

# Install dependencies
# No requirements.txt detected

# Run the project
python main.py

# Run tests
pytest
```

## How it works

Estrutura limpa e modular com separação de responsabilidades.

---

## Capabilities

| Capability | Description |
|------------|-------------|
| Data Loading | Auto-download TensorFlow creditcard.csv (284k transactions) with local caching |
| EDA & Visualization | Class distribution, Amount histograms, correlation heatmaps (matplotlib/seaborn) |
| Preprocessing | RobustScaler on Amount/Time, stratified split, duplicate removal |
| Balancing | SMOTE oversampling (fallback: class_weight="balanced") |
| Modeling | LogisticRegression, RandomForest, ExtraTrees with RandomizedSearchCV (StratifiedKFold) |
| Metrics | Accuracy, Precision, Recall, F1, ROC AUC, Specificity, Confusion Matrix |
| Selection | Weighted score: Recall 40% + F1 30% + Precision 20% + Accuracy 10% |
| Persistence | joblib serialization for model, scaler, and full results |


---



---

## FAQ

<details>
<summary><strong>What is this project?</strong></summary>

A Python study/project demonstrating core concepts.

</details>

<details>
<summary><strong>How do I run it?</strong></summary>

See [Quick Start](#quick-start) for copy-paste commands.

</details>

<details>
<summary><strong>Are there tests?</strong></summary>

No automated tests in this repository.

</details>

<details>
<summary><strong>Can I use this in production?</strong></summary>

This is a **study/portfolio project**. Review and harden (auth, persistence, monitoring, etc.) before production use.

</details>



---

## Documentation

- **Source Code** ,  Browse the `src/` directory for implementation details
- **API Reference** ,  Inline docstrings + type hints
- **Architecture Diagram** ,  See [architecture.mermaid](docs/architecture.mermaid) (if present)
- **Changelog** ,  [CHANGELOG.md](CHANGELOG.md) (if present)
- **Contributing** ,  [CONTRIBUTING.md](CONTRIBUTING.md) (if present)

## License

[MIT](LICENSE) ,  Kelvin Oliveira

---

<div align="center">

**Built with** · Python 3 + scikit-learn + pandas

**Author** · [Kelvin Oliveira](https://github.com/KelvinOliveiraCode) · [Portfolio](https://kelvinoliveiracode.github.io/portfolio/)

</div>