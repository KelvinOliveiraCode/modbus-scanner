# modbus-scanner

[![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://www.python.org/)   ![status: concluido](https://img.shields.io/badge/status-concluido-green)   ![licenca: MIT](https://img.shields.io/badge/licenca-MIT-blue)

## Resumo

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores
## Problema / Por que existe

O projeto aborda um recorte prático e automatiza uma tarefa que, feita manualmente, é repetitiva e propensa a erro. O foco está em transformar dados ou processos em saída confiável, com código legível, testável e extensível.
## Arquitetura

O código está organizado por responsabilidade em 0 classes principais:
## O que faz

Protocolo Modbus TCP do zero: servidor de lab, scanner e leitura de medidores
## Como rodar

Requisitos: Python 3.x instalado.

```bash
# instalar dependências (se houver requirements.txt)
# sem requirements.txt detectado
```

```bash
# executar
python main.py
```

```bash
# executar testes
pytest
```
## Estrutura do Projeto (Classes Principais)


## Trade-offs e Decisões Técnicas

- Biblioteca padrão sempre que possível; dependências externas só quando o ganho justifica a manutenção.
- Pipeline linear e modular: cada etapa (EDA, pré-processamento, balanceamento, modelagem, avaliação) é uma função isolada, facilitando testes e substituição.
- SMOTE opcional com fallback para `class_weight="balanced"` quando `imbalanced-learn` não está instalado.
- `RobustScaler` aplicado apenas em `Amount` e `Time`; features anonimizadas (V1-V28) já normalizadas no dataset original.
- Seleção de modelo por score ponderado: Recall(40%) + F1(30%) + Precision(20%) + Accuracy(10%) ,  prioriza detecção de fraudes (recall) sem ignorar precisão.
- Artefatos salvos via `joblib`: modelo, scaler e resultados completos para reprodutibilidade.
## Limitações Conhecidas

- Escopo limitado ao pipeline de detecção de fraude; não é uma plataforma ML completa.
- Depende de Python 3.x e das bibliotecas listadas no `requirements.txt`.
- SMOTE só disponível se `imbalanced-learn` estiver instalado; caso contrário usa `class_weight`.
- Dataset fixo (creditcard.csv do TensorFlow); não há pipeline de ingestão de novos dados.
- Modelos treinados em CPU; não há suporte a GPU/TPU configurado.
## Testes

```bash
pytest
```
Nenhum teste automatizado detectado na varredura.
## Licença

Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` do repositório.
## Autor

Kelvin Oliveira ,  https://github.com/KelvinOliveiraCode
Portfolio: https://kelvinoliveiracode.github.io/portfolio/
