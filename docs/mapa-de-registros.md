# Mapa de registradores

O protocolo Modbus so transporta inteiros de 16 bits. O significado do
endereco 0, a unidade e a escala ficam fora do protocolo: sao documentacao do
fabricante. Este documento e essa documentacao.

O mapa vive em `dados/mapa-de-registros.yaml` e e carregado por
`modbuslab.registros.carregar_mapa`. Ver a tabela a seguir com
`python -m modbuslab mapa`.

## Escala

Um medidor que mede 219,4 V nao manda 219,4. Ele manda um inteiro, e o mapa
diz como voltar ao valor real:

```
bruto = valor * escala
valor = bruto / escala
```

Com `escala: 10`, um registrador que vale 2194 no fio significa 219,4 V. Com
`escala: 1000`, um registrador que vale 939 significa 0,939 de fator de
potencia.

A conversao e a mesma nos dois sentidos, com o mesmo par de funcoes. Nao existe
escala so na leitura, o que faria o servidor e o cliente discordarem do
mesmo numero.

## Registrador de 32 bits

Energia acumulada estoura 16 bits cedo. Um medidor que passou de 65535 kWh nao
cabe em um registrador de 16 bits, e a solucao no mundo real e ocupar **dois
enderecos**.

Os tipos `uint32` e `int32` fazem isso. A ordem das palavras e a de uso comum em
automacao, a convencao Modicon: **palavra alta primeiro**, ou seja, o endereco
menor guarda a parte alta.

Para 91240 kWh:

```
91240 = 0x00016468

endereco 11: 0x0001   (palavra alta)
endereco 12: 0x6468   (palavra baixa)
```

O mapeamento reserva os dois enderecos. Registrar `energia` no endereco 11
depois de usar o 12 levanta erro na carga do mapa, e nao silenciosamente no
primeiro atendimento.

Um detalhe do fio que costuma passar batido: cada palavra ocupa o **proprio
endereco**. Uma leitura de bloco que pega so o endereco 11 devolve a palavra
alta, e um cliente que decodificasse isso como valor completo leria 65536 em vez
de 91240. Foi o que aconteceu na primeira versao deste servidor, que emitia a
palavra alta no endereco de inicio e zero no seguinte.

## medidor_1pn, medidor monofasico

| End | Registrador | Tipo | Pal | Escala | Unidade | Descricao |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 0 | `tensao` | uint16 | 1 | 10 | V | Tensao fase-neutro |
| 1 | `corrente` | uint16 | 1 | 100 | A | Corrente na fase |
| 2 | `potencia_ativa` | uint16 | 1 | 1 | W | Potencia ativa instantanea |
| 3 | `potencia_reativa` | int16 | 1 | 1 | var | Potencia reativa instantanea |
| 4 | `energia` | uint32 | 2 | 1 | kWh | Energia ativa acumulada |
| 6 | `frequencia` | uint16 | 1 | 100 | Hz | Frequencia da rede |
| 7 | `fator_potencia` | uint16 | 1 | 1000 | | Fator de potencia medido |

O mapa ocupa 8 enderecos: os 4 a 5 sao as duas palavras de `energia`, e por isso
`frequencia` comeca no 6 e nao no 5.

## medidor_3pn, medidor trifasico

| End | Registrador | Tipo | Pal | Escala | Unidade | Descricao |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 0 | `tensao_l1` | uint16 | 1 | 10 | V | Tensao da fase L1 |
| 1 | `tensao_l2` | uint16 | 1 | 10 | V | Tensao da fase L2 |
| 2 | `tensao_l3` | uint16 | 1 | 10 | V | Tensao da fase L3 |
| 3 | `corrente_l1` | uint16 | 1 | 100 | A | Corrente da fase L1 |
| 4 | `corrente_l2` | uint16 | 1 | 100 | A | Corrente da fase L2 |
| 5 | `corrente_l3` | uint16 | 1 | 100 | A | Corrente da fase L3 |
| 6 | `angulo_l1` | uint16 | 1 | 10 | graus | Angulo de fase de L1 |
| 7 | `angulo_l2` | uint16 | 1 | 10 | graus | Angulo de fase de L2 |
| 8 | `angulo_l3` | uint16 | 1 | 10 | graus | Angulo de fase de L3 |
| 9 | `potencia_ativa` | uint16 | 1 | 1 | W | Soma das potencias ativas |
| 10 | `potencia_reativa` | int16 | 1 | 1 | var | Soma das potencias reativas |
| 11 | `energia` | uint32 | 2 | 1 | kWh | Energia ativa acumulada |
| 13 | `frequencia` | uint16 | 1 | 100 | Hz | Frequencia da rede |
| 14 | `fator_potencia` | uint16 | 1 | 1000 | | Fator de potencia medido |

O mapa ocupa 15 enderecos. As tensao e as correntes sao por fase; o consumo
agrega. A tensao reportada e a media das tres, que e a tensao de linha, e a
corrente e a soma das correntes de fase.

### Por que angulo e nao tensao

`angulo_l1`, `angulo_l2` e `angulo_l3` existem para detectar sequencia de fase
invertida, e nao por enfeite.

Sequencia de fase e uma propriedade **angular**. Num sistema trifasico
balanceado, as tres tensao linha-a-linha tem o mesmo valor RMS nas duas
sequencias: em L1-L2-L3 e em L1-L3-L2, com 220 V em qualquer das tres, o valor
RMS e identico. So o sentido de rotacao difere.

Qualquer heuristica baseada em magnitude nao pode distinguir os dois casos. E o
pior: como as tres tensoes saem iguais, a heuristica tenderia a dizer "normal"
sempre, e nunca acusaria o erro de campo mais comum em instalacao trifasica.

Num sistema ideal, com L1 como referencia em 0 graus:

```
sequencia positiva (L1-L2-L3):  L1 =   0   L2 = -120   L3 = +120
sequencia negativa (L1-L3-L2):  L1 =   0   L2 = +120   L3 = -120
```

O salto de L1 para L2, medido no sentido positivo, vale 240 graus na sequencia
positiva e 120 graus na negativa. E sobre esse salto que o detector decide, com
20 graus de tolerancia para ruido de medicao, e usando dois saltos
independentes: se um deles for ilegivel ou os dois discordarem, o veredito e
indeterminado em vez de uma escolha arbitraria.

Quando a tensao esta desbalanceada alem de 10%, o angulo medido deixa de
descrever a sequencia com seguranca, e o detector diz isso em vez de chutar.

## medidor_demanda, medidor de demanda

| End | Registrador | Tipo | Pal | Escala | Unidade | Descricao |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 0 | `demanda_ativa` | uint16 | 1 | 1 | W | Demanda ativa maxima da janela |
| 1 | `demanda_reativa` | int16 | 1 | 1 | var | Demanda reativa maxima |
| 2 | `energia_acumulada` | uint32 | 2 | 1 | kWh | Energia acumulada |
| 4 | `tensao` | uint16 | 1 | 10 | V | Tensao de referencia do barramento |
| 5 | `corrente` | uint16 | 1 | 100 | A | Corrente total |
| 6 | `frequencia` | uint16 | 1 | 100 | Hz | Frequencia da rede |
| 7 | `fator_potencia` | uint16 | 1 | 1000 | | Fator de potencia medido |

Usa `demanda_*` em vez de `potencia_*`, que e como medidor de demanda real se
identifica. O calculador aceita os dois nomes.

## Tipos suportados

| Tipo | Bytes | Faixa | Palavras |
| --- | ---: | --- | ---: |
| `uint16` | 2 | 0 a 65535 | 1 |
| `int16` | 2 | -32768 a 32767 | 1 |
| `uint32` | 4 | 0 a 4294967295 | 2 |
| `int32` | 4 | -2147483648 a 2147483647 | 2 |

Os tipos com sinal usam complemento a dois, que e o que o protocolo transporta
como padrao.

## Validacao na carga

Os valores em `dados/dispositivos.yaml` sao de **engenharia**, nao os brutos do
fio, e o carregador converte e valida cada um contra o tipo do registrador.

Isso pega erro de digitacao na hora de subir o servidor, e nao na primeira
leitura, quando o valor invalido ja foi gravado no medidor. Um
`fator_potencia: 962` no lugar de `0.962` estoura `uint16` com escala 1000, e o
carregamento falha com o nome do registrador e a faixa aceita.

## Adicionar um registrador

1. Acrescente o item ao mapa em `dados/mapa-de-registros.yaml`, com endereco
   livre. A carga recusa endereco ja ocupado.
2. Se for de 32 bits, lembre que ele reserva o endereco seguinte.
3. Reinicie o servidor. O novo registrador passa a ser servido no endereco.

Nao ha codigo a alterar: o servidor e o cliente leem do mapa, e o calculador
busca pelo nome.