# Protocolo Modbus TCP: enquadramento, funcao e ausencia de seguranca

Este documento explica o que o `modbuslab` implementa do zero: o cabecalho
MBAP, o PDU, as funcoes de leitura, as excecoes, e por que o protocolo e
estruturalmente sem seguranca.

## O quadro

Uma mensagem Modbus TCP e um cabecalho de 7 bytes seguido do PDU:

```
+------+--------+--------+--------+--------+---+-------+
|      |        |        |        |        |   |       |
+------+--------+--------+--------+--------+---+-------+
|  Transaction  | Protocol |    Length     |Unit|  PDU  |
|  identifier   |  ident.  |  do PDU + UI  | id |       |
+------+--------+--------+--------+--------+---+-------+
     2 bytes      2 bytes     2 bytes      1    1 a 253
```

Com os numeros do exemplo, uma leitura de um registrador no endereco 0:

```
00 01   00 00   00 06   01   04   00 00   00 01
|     |      |      |     |    |     |     |
|     |      |      |     |    |     |     +-- quantidade: 1
|     |      |      |     |    |     +-------- endereco: 0
|     |      |      |     |    +-------------- funcao: 4, read input registers
|     |      |      |     +------------------- unit id: 1
|     |      |      +------------------------- comprimento: 6
|     |      +-------------------------------- protocolo: 0, sempre Modbus TCP
+-------------+-------------------------------- transacao: 1
```

Doze bytes no total.

## O erro do campo comprimento

O campo `Length` conta os bytes que vem **depois** dele: o unit id mais o PDU.
O exemplo acima declara 6, e o quadro tem 6 + 6 = 12 bytes, nao 7 + 6 = 13.

Somar os 7 bytes do MBAP inteiro ao comprimento produz um quadro um byte maior
do que o cliente envia. O servidor, ao interpretar o cabecalho, calcula um total
que nunca chega, e a conexao trava esperando um byte que nao existe. Foi
exatamente o que aconteceu na primeira versao deste projeto, e o sintoma era
simples: todo cliente expirava por timeout, com o servidor aparentemente vivo.

O nome da constante em `protocolo.py` diz isso para quem chega depois:

```python
#: O campo de comprimento conta o que vem DEPOIS dele, ou seja, o unit id e o
#: PDU. Por isso o quadro inteiro tem ``6 + comprimento`` bytes e nao
#: ``7 + comprimento``.
BYTES_ANTES_DO_COMPRIMENTO = 6
```

## Resposta de sucesso e resposta de excecao

Uma leitura bem-sucedida devolve a funcao, a contagem de bytes e os dados:

```
00 01   00 00   00 05   01   04   02   08 92
                                  |    +------ dados: 2194
                                  +----------- 2 bytes de dados
```

Uma recusa troca o codigo de funcao pelo mesmo codigo com o bit 0x80 ligado, e
o byte seguinte e o codigo de excecao:

```
00 01   00 00   00 03   01   83   02
                       |    |    +------ excecao 2: endereco de dado invalido
                       |    +----------- 0x03 | 0x80 = funcao 3 com bit de excecao
                       +------------------- unit id ecoado
```

Nove bytes. E por isso que o cliente deste projeto le primeiro o MBAP, que ja
declara o comprimento, e so entao le o resto. Assumir `9 + 2 * quantidade`
bytes trava o cliente em toda resposta de excecao.

## Funcoes

| Codigo | Nome | Direcao | O que faz |
| --- | --- | --- | --- |
| 0x03 | Read Holding Registers | leitura | registradores que aceitam leitura e escrita |
| 0x04 | Read Input Registers | leitura | registradores somente de leitura |
| 0x06 | Write Single Register | escrita | grava um registrador |
| 0x10 | Write Multiple Registers | escrita | grava um bloco |

O lab implementa 3 e 4. As duas de escrita nao sao implementadas de proposito:
uma ferramenta de leitura de consumo nao precisa escrever em medidor, e deixar a
escrita ausente faz o servidor responder excecao 1 em vez de aceitar um comando
que so o teste usaria.

A distincao entre holding e input nao e decorativa. Registrador de holding e
configuravel: mudar a escala de um medidor e mudar o endereco do relogio. Por
isso a varredura usa funcao 4, que e somente leitura e nao tem efeito colateral.

## Excecoes

| Codigo | Nome | Quando |
| --- | --- | --- |
| 0x01 | Illegal Function | funcao que este servidor nao implementa |
| 0x02 | Illegal Data Address | endereco de registrador que o dispositivo nao tem |
| 0x03 | Illegal Data Value | quantidade fora de 1 a 125, ou quadro truncado |

## Unit id e o endereco de quem responde

O unit id do MBAP e o endereco do dispositivo no barramento. E por ele que dois
medidores podem ter o registrador 0 com valores diferentes e continuarem sendo
dois medidores.

Um device Modbus de campo, ao receber um quadro cujo unit id nao e o seu,
**descarta o quadro sem responder**. Isso e diferente de excecao 2, que responde
a endereco de registrador invalido em um unit que existe. Um device que
respondesse excecao 2 para todo unit id desconhecido transforms a varredura em
algo instantaneo e sem informacao; o silencio e o que faz a varredura custar
tempo, porque o cliente precisa esperar o timeout antes de concluir que o
endereco esta livre.

Este laboratorio descarta, como o device de campo.

## Tres coisas que um exemplo ingenuo erra

**Despachar por endereco em vez de unit id.** Um servidor que ignora o unit id e
concatena os registradores de todos os dispositivos responde com a fila errada
para um cliente que pediu uma coisa so.

**Assumir que recv devolve o quadro inteiro.** Nao devolve. `recv` entrega o que
chegou ate agora, e um pedido de 12 bytes pode chegar em duas chamadas. O
servidor acumula em buffer, e so interpreta quando tem MBAP mais PDU.

**Atender uma requisicao por conexao.** O cliente de polimento mantem a conexao
aberta e reusa. Um servidor que fecha depois da primeira resposta obriga o
cliente a reconectar a cada leitura.

## Por que Modbus TCP nao tem seguranca

Nao e falha de implementacao. O protocolo nasceu em 1979 para ligar um terminal
programavel a um controlador de linha dentro de uma planta, num barramento de
cobre onde o controle de acesso era fisico: o cabo. Nao ha:

- **autenticacao**: qualquer um que chegue ao socket fala com o medidor;
- **cifragem**: toda leitura e toda escrita trafega em texto claro no fio;
- **integridade**: nao ha checksum nem assinatura, entao um quadro pode ser
  adulterado no caminho;
- **autorizacao por objeto**: quem escreve num holding register escreve em
  qualquer um deles.

Um concentrador Modbus exposto a uma rede IP nao gerenciada pode estar dentro do
predio, num enlace que ninguem monitora, e ainda assim sem nenhum controle.

Por isso Modbus TCP nunca deve sair do segmento onde ele foi pensado. Quando
precisa de rede longa, o caminho e uma tunelizacao, com autenticacao e cifragem
na borda. O `modbuslab` escuta apenas em `127.0.0.1`, e nao aceita outro host
como padrao, pelo mesmo motivo.

O mesmo raciocinio aparece nos medidores de energia para IP: quem le o consumo de um
medidor tambem pode reescrever o relogio, se o medidor expor holding registers
de configuracao. Por isso leitura e escrita sao funcoes separadas no
protocolo, e por isso este lab so implementa as de leitura.