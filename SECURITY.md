# Politica de seguranca

## Versoes suportadas

Correcoes de seguranca sao aplicadas na versao mais recente publicada do
modbuslab. Atualize antes de reportar um problema que talvez ja esteja
resolvido.

| Versao | Recebe correcoes |
|---|---|
| 1.0.x | Sim |

## Como reportar uma vulnerabilidade

Nao divulgue vulnerabilidade, prova de conceito, credencial, binario privado
ou qualquer artefato de ambiente em issue publica.

Use **Report a vulnerability**, na aba **Security** do repositorio, para
enviar o relato em privado. Nao abra issue publica para pedir um canal de
contato privado.

Inclua no relato privado:

- a versao do modbuslab, do Python e do sistema operacional;
- o que o problema faz e o que ele deveria fazer;
- os passos de reproducao, com o comando exato e a saida;
- o que voce tentou e o que aconteceu;
- qualquer mitigacao que voce sugira.

Remova credencial, token, caminho privado e dado de ambiente dos logs e
exemplos.

O mantenedor vai confirmar o recebimento, avaliar o escopo e combinar a
correcao e a divulgacao com quem reportou.

## Fronteira de seguranca

Vale saber o que este projeto e, e o que ele nao e.

**O que o modbuslab e.** Um laboratorio local que implementa o protocolo
Modbus TCP sobre socket da biblioteca padrao do Python, com dados de medidor
ficticios. Ele roda em loopback.

**O que o modbuslab nao e, e nao pretende ser.**

- **Nao e um simulador de campo.** Nao tem autenticacao, autorizacao, lista
  de dispositivos autorizados, nem registro de operacao. Qualquer cliente que
  alcance a porta tem o que o servidor oferece.
- **Nao protege o dado.** O Modbus TCP, em si, nao tem seguranca: o quadro
  viaja em claro, sem autenticacao e sem cifragem. O guia do protocolo em
  [`docs/protocolo-modbus-tcp.md`](docs/protocolo-modbus-tcp.md) explica a
  estrutura e por que o protocolo e estruturalmente sem seguranca.
- **Nao e sandbox.** Ele nao analisa binario, nao executa codigo do alvo e nao
  contem processo nenhum.
- **Nao tem persistencia.** Os valores de cada medidor existem enquanto o
  processo roda. Um processo novo comeca do zero.
- **Nao e Multi-Mestre.** O servidor atende um cliente por vez. Uma segunda
  conexao espera a primeira terminar.

## O laboratorio nao escuta fora do loopback

Por padrao, `servidor`, `varrer` e `ler` usam `127.0.0.1`. O parametro
`--host` permite mudar isso, e a essa altura a decisao e de quem opera a
maquina. O modbuslab nao abre porta publica sozinho, e nao instala nem
configura nada no sistema.

Se voce expor o servidor em uma interface de rede, saiba que nao existe
autenticacao: qualquer um que alcance a porta consegue ler os registradores.

## Dependencias

O projeto tem uma unica dependencia de runtime, `PyYAML`, usada para ler os
arquivos de dados. As demais sao de desenvolvimento e nao entram no pacote
instalado.
