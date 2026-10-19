# Arquitetura

Este guia explica como o modbuslab esta organizado e por que a organizacao e
essa. O diagrama completo esta em [`architecture.mermaid`](architecture.mermaid).

## A ideia em uma frase

O protocolo e o formato do fio, e ele nao pertence a nenhum lado: servidor e
cliente usam a mesma implementacao, como acontece em qualquer implementacao
real do Modbus TCP.

## As camadas

O codigo esta em `src/modbuslab/`, e as dependencias correm para dentro.

### `protocolo.py` — o formato do fio

Nao importa nada do resto do projeto. E o cabecalho MBAP, o PDU, os codigos de
excecao e as funcoes que empacotam e desempacotam quadros.

Este modulo e a base de tudo. Se a formacao de um quadro mudar, todo o resto
muda junto, e por isso ele nao depende de ninguem: quem depende dele nao pode
puxar o resto de volta.

O guia [`protocolo-modbus-tcp.md`](protocolo-modbus-tcp.md) explica o MBAP, o
PDU e por que o protocolo e estruturalmente sem seguranca.

### `registros.py` — o mapa de registradores

Cada registrador tem endereco, tipo, escala e faixa. O modulo sabe converter
palavras do fio em valor de engenharia e vice versa, e sabe montar o mapa a
partir de um YAML.

O ponto que costuma ser mal explicado: o protocolo Modbus nao diz o que um
registrador significa. O cliente precisa levar o mapa junto, porque o mapa e
documentacao.

### `dispositivos.py` — os medidores

Um medidor tem unit id, mapa de registradores, valores correntes e numero de
fases. O `GerenciadorDispositivos` eh o conjunto que um servidor serve, e ele
recusa unit id repetido.

O carregador valida cada valor do YAML contra o tipo do registrador no momento
do carregamento. Um valor fora da faixa falha ali, e nao no primeiro
atendimento do servidor, onde seria bem mais dificil de diagnosticar.

### `consumo.py` — o calculo eletrico

Fator de potencia, potencia aparente, energia acumulada, sequencia de fase e
desbalanco. Nao importa nenhum outro modulo do projeto: e matematica, e
matematica nao deveria conhecer socket nem YAML.

### `servidor.py` — o servidor TCP

Aceita conexao, le o stream, monta o buffer ate ter um quadro completo, e
atende pedido por pedido.

Tres coisas que um servidor de campo faz e que um exemplo ingenuo erra, e que
estao implementadas aqui:

- **Despacho por unit id.** Dois medidores podem ter o registrador 0 com
  valores diferentes e continuam sendo dois medidores. Um servidor que ignora o
  unit id responde com a fila errada.
- **Leitura parcial de TCP.** `recv` devolve o que chegou ate agora, nao o
  quadro inteiro. O servidor acumula em buffer ate ter MBAP mais PDU.
- **Varias requisicoes por conexao.** O cliente mantem a conexao aberta, e o
  servidor precisa atender em ciclo, nao fechar depois da primeira resposta.

Limitacao conhecida: o servidor atende um cliente por vez. A segunda conexao
espera a primeira terminar. Isso nao e problema no laboratorio, em que o
cliente fecha a conexao e abre outra.

Unit id desconhecido recebe silencio, e nao excecao 2. Excecao 2 responde a
endereco de registrador invalido em um unit que existe; unit id desconhecido
nao existe, e responder a ele seria inventar um dispositivo.

### `scanner.py` — o cliente e a varredura

O `ClienteModbus` fala o protocolo sobre um socket, e o `ScannerModbus`
percorre um intervalo de unit ids e registra quem respondeu. O scanner nao
conhece a lista de medidores: ele descobre.

E por isso que o silencio do servidor em unit id desconhecido tem custo: a
varredura precisa esperar o timeout de cada id que nao existe.

### `cli.py` — a entrada

Monta o parser, chama o comando e renderiza o resultado. Nao contem regra de
negocio: quem decide e o modulo abaixo dela.

A CLI fala o mesmo idioma do resto do projeto, em portugues, e as mensagens
sao bilingues quando o texto aparece na saida.

## As dependencias, em uma linha

```
cli  ->  servidor  ->  protocolo
     ->  scanner   ->  protocolo
     ->  dispositivos -> registros
     ->  consumo
```

`consumo` nao depende de ninguem. `protocolo` nao depende de ninguem.
`registros` nao depende de ninguem dentro do projeto.

## Onde os dados moram

`dados/` tem dois YAML:

- `mapa-de-registros.yaml` define os registradores de cada tipo de medidor.
- `dispositivos.yaml` define os medidores do laboratorio e os valores de
  engenharia iniciais.

Os valores sao ficticios. O medidor trifasico esta com a sequencia de fase
invertida de proposito, e o comentario no proprio YAML explica por que: e o
erro de campo classico de instalacao trifasica, e e o que o scanner precisa ter
o que encontrar.

## Onde a verificacao mora

| Onde | O que verifica |
|---|---|
| `tests/` | Uma classe de teste por modulo, mais `test_api.py` para o contrato publico do pacote. |
| `tools/verificar_aceite.py` | O fluxo inteiro: subir o lab, varrer, ler os tres medidores pela rede, achar a sequencia invertida e bater o consumo com os registradores. |
| `tools/gerar_exemplos.py` | Regenera `exemplos/` a partir da saida real, e o CI falha se o arquivo commitado divergir. |
| `tools/verificar_encoding.py` | Que nenhum arquivo de texto tenha caractere corrompido. |

A suite prova que cada funcao funciona. A prova de aceite prova o que a suite
nao prova sozinha. As duas existem porque respondem a perguntas diferentes.

## Onde mudar o que

| Se voce quer mudar... | Va para... |
|---|---|
| A formacao de um quadro no fio | `protocolo.py`, e o guia `protocolo-modbus-tcp.md` junto |
| A escala de um registrador | `dados/mapa-de-registros.yaml` |
| Os medidores do laboratorio | `dados/dispositivos.yaml` |
| O calculo eletrico | `consumo.py` |
| O texto e o formato da saida da CLI | `cli.py` |
| O comportamento do servidor na rede | `servidor.py` |
