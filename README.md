# modbus-scanner

<div align="center">

[English](README.en.md) · **Português (Brasil)**

</div>

[![Python 3](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikit-learn)](https://scikit-learn.org/) [![pandas](https://img.shields.io/badge/pandas-150458?style=flat-square&logo=pandas)](https://pandas.pydata.org/) [![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest)](https://docs.pytest.org/) [![MIT License](https://img.shields.io/badge/License-MIT-f4c430?style=flat-square)](LICENSE)

### Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

---

## O que é

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores

---

## Início Rápido

```bash
# Clone e entre
git clone https://github.com/KelvinOliveiraCode/<repo>.git
cd <repo>

# Instale dependências
# Nenhum requirements.txt detectado

# Execute o projeto
python main.py

# Execute os testes
pytest
```

## Como funciona

Estrutura limpa e modular com separação de responsabilidades.

---

## Capacidades

| Capacidade | Descrição |
|------------|-------------|
| Carregamento de Dados | Auto-download do TensorFlow creditcard.csv (284k transações) com cache local |
| EDA e Visualização | Distribuição de classes, histogramas de Amount, heatmaps de correlação (matplotlib/seaborn) |
| Pré-processamento | RobustScaler em Amount/Time, split estratificado, remoção de duplicatas |
| Balanceamento | SMOTE oversampling (fallback: class_weight="balanced") |
| Modelagem | LogisticRegression, RandomForest, ExtraTrees com RandomizedSearchCV (StratifiedKFold) |
| Métricas | Accuracy, Precision, Recall, F1, ROC AUC, Specificity, Confusion Matrix |
| Seleção | Score ponderado: Recall 40% + F1 30% + Precision 20% + Accuracy 10% |
| Persistência | Serialização joblib para modelo, scaler e resultados completos |


---



---

## Perguntas Frequentes

<details>
<summary><strong>O que é este projeto?</strong></summary>

Um estudo/projeto em Python demonstrando conceitos fundamentais.

</details>

<details>
<summary><strong>Como executar?</strong></summary>

Veja [Início Rápido](#início-rápido) para comandos copiáveis.

</details>

<details>
<summary><strong>Há testes?</strong></summary>

Nenhum teste automatizado neste repositório.

</details>

<details>
<summary><strong>Posso usar em produção?</strong></summary>

Este é um **projeto de estudo/portfólio**. Revise e endureça (auth, persistência, monitoramento, etc.) antes de usar em produção.

</details>



---

## Documentação

- **Código-Fonte** ,  Navegue pelo diretório `src/` para detalhes de implementação
- **Referência da API** ,  Docstrings inline + type hints
- **Diagrama de Arquitetura** ,  Veja [architecture.mermaid](docs/architecture.mermaid) (se presente)
- **Changelog** ,  [CHANGELOG.md](CHANGELOG.md) (se presente)
- **Contribuindo** ,  [CONTRIBUTING.md](CONTRIBUTING.md) (se presente)

## Licença

[MIT](LICENSE) ,  Kelvin Oliveira

---

<div align="center">

**Construído com** · Python 3 + scikit-learn + pandas

**Autor** · [Kelvin Oliveira](https://github.com/KelvinOliveiraCode) · [Portfolio](https://kelvinoliveiracode.github.io/portfolio/)

</div>