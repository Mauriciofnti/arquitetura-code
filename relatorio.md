# Projeto Aulas 16–17 — Extrair ou não extrair: Notificações

**Alunos:** Kelvin e Maurício

---

## Cenário

**Sistema:** Marketplace Orion (grafo das Aulas 7 e 12), 10 componentes, 17 arestas.
**Origem dos dados:** grafo didático fornecido em `quantum.py`; **não são medições do Orion** —
as taxas de falha e disponibilidade são hipóteses de trabalho.
**Candidato à extração:** `Notificacoes`.
**Motivador de separação:** **isolamento de falha + assincronia natural**.
Notificações recebe de 4 componentes (Pedidos, Pagamentos, Logística, Integrações), e todas as
chamadas que chegam são efeitos de comunicação (e-mail, push, SMS) que não precisam bloquear o
fechamento da compra. Se Notificações cai, o pedido ainda deve fechar. O motivador é **alegado**,
não medido — a Parte 2 e o ADR vão testá-lo.

---

## Parte 1 — Custo da rede (`meu_ensaio.py`)

**Hipóteses trocadas (Opção A):**
- `latencia_mediana = 0.050` (50 ms) — meta de p50 de provedor cloud para chamada intra-região.
- `latencia_p99 = 0.800` (800 ms) — p99 típico de chamada entre zonas de disponibilidade.
- `taxa_falha = 0.005` (0,5%) — premissa de SLO de 99,5% por chamada.

### 1.1 Linha de base

**Painel (2 tentativas, sem chave, semente 42):**

| métrica | valor |
|---|---:|
| mediana | 51 ms |
| p95 | 395 ms (meta 2000 ms) |
| p99 | 951 ms |
| esperaram timeout inteiro | 20 (1,00%) |
| cobrados duas vezes | 18 (0,90%) |
| "não sei" | 0 |

**Políticas (2000 fechamentos, semente 42):**

| política | sem resposta | duplicadas | cobrado s/ pedido | pior |
|---|---:|---:|---:|---:|
| não repetir (1) | 20 | 0 | 18 | 1,00s |
| repetir sem chave (2) | 0 | 18 | 0 | 1,42s |
| repetir com chave (2) | 0 | 0 | 0 | 1,42s |
| repetir com chave (3) | 0 | 0 | 0 | 1,42s |
| repetir sem chave (3) | 0 | 18 | 0 | 1,42s |

**Varredura (10 sementes, repetir sem chave):** p95 entre 345–399 ms; timeout inteiro entre
0,90%–1,45%; duplicadas entre 0,65%–1,30%.

**O que muda entre sementes:** os números de timeout e duplicadas oscilam — semente 1 dá 1,45%
e 1,30%; semente 7 dá 0,90% e 0,65%. A rede simulada é aleatória, então a semente muda quais
chamadas caem no timeout.
**O que não muda:** a política "com chave" mantém duplicadas em **0** em todas as sementes —
é estrutural (depende da lógica do servidor, não do sorteio). E "não repetir" sempre gera
"cobrado sem pedido" > 0 (18 na semente 42), enquanto as políticas com chave nunca geram.

### 1.2 Hipóteses próprias

Com `MEU_CENARIO` (50 ms / 800 ms / 0,5%), a tabela de políticas mantém o mesmo padrão
qualitativo da linha de base.

**Sobrevive:** "sem chave duplica, com chave não duplica" — **estrutural**, não depende dos valores.
**Muda:** o número absoluto de timeout cai com a taxa de falha menor (0,5% vs. 2%); o p99 cai
para ~951 ms (vs. o p99 da campanha original, que era maior). O pior caso (1,42s) é dominado pelo
timeout de 1s, não pela latência mediana.

### 1.3 Previsão antes de rodar — e o que aconteceu

**Previsão escrita antes:** *"com 3 tentativas sem chave, as duplicadas serão maiores que com 2
(cada tentativa extra é uma nova chance de executar de novo quando a resposta se perde); os
'não sei' serão menores (mais tentativas, mais chance de ao menos uma resposta chegar)."*

**Resultado real:**

| política | sem resposta | duplicadas |
|---|---:|---:|
| repetir sem chave (2) | 0 | **18** |
| repetir sem chave (3) | 0 | **18** |

**A previsão falhou na magnitude:** as duplicadas **não aumentaram** (18 = 18), e os "não sei"
já eram 0 com 2 tentativas, então não podiam cair. **O que faltou no raciocínio:** com
`taxa_falha = 0,005`, a chance de as **duas primeiras** tentativas falharem é `0,005² = 0,0025%` —
em 2000 rodadas, espera-se ~0,05 caso. Ou seja, **a 3ª tentativa quase nunca é exercitada**: as
duas primeiras já resolvem. O mecanismo que eu previ (mais tentativas → mais chance de duplicar)
está certo, mas **só se manifesta quando a taxa de falha é alta o suficiente para a 3ª tentativa
ser acionada**. Com 0,5%, o efeito é invisível. **Conclusão:** a previsão qualitativa valeria com
taxa de falha de 2% (como no `ensaio.py` original); com a minha hipótese de 0,5%, o número não muda.

### 1.4 Interpretação

Para Notificações, adotaria **"repetir com chave (3)"** — duplicadas = 0, sem resposta = 0, e a
3ª tentativa é barata porque só é acionada em falha dupla (rara com 0,5%). Mas, como Notificações
é **assíncrona por natureza**, o mais correto é **enfileirar e deixar o consumidor idempotente
repetir**, em vez de repetir sincronamente no fechamento — isso tira a latência da 2ª/3ª
tentativa do caminho crítico do pedido.
**O ensaio não mede** o custo de guardar as chaves idempotentes (estado persistente) nem a espera
entre tentativas (backoff).

---

## Parte 2 — Forma de implantação (`meu_quantum.py`)

### 2.1 Grafo

Mantido o grafo do Orion (10 componentes, 17 arestas); `ORIGEM_DO_FLUXO = "Checkout"`,
`DESTINO_DA_FILA = "Notificacoes"`. Substituídas as formas antigas pelas três do item 2.2.

### 2.2 Formas

1. `forma_monolito()` — 1 artefato.
2. `forma_extracao_notificacoes()` — 2 artefatos (`orion` + `notificacoes`).
3. `forma_service_based_por_dominio()` — 8 artefatos (os oito módulos da Aula 12).
(4.) `forma_microsservicos()` — 10 artefatos, usada como teto de comparação.

### 2.3 Conta à mão × código

| forma | artefatos | remotas | diretas | q_sync (banco comp.) | q_fila (banco comp.) | q_sync (banco/serviço) | q_fila (banco/serviço) |
|---|---:|---:|---:|---:|---:|---:|---:|
| monólito modular | 1 | 0 | 0 | 1 | 1 | 1 | 1 |
| extração de Notificações | 2 | 4 | 0 | 1 | 1 | 1 | 2 |
| service-based (8 domínios) | 8 | 15 | 4 | 1 | 1 | 1 | 2 |
| microsserviços (10) | 10 | 17 | 5 | 1 | 1 | 10 | 7 |

**Conta à mão do service-based (detalhada):**
- 8 artefatos (um por módulo: Borda, Vitrine, Compra, Financeiro, Distribuicao, Comunicacao,
  Identidade, Integracao).
- Das 17 arestas, **2 são internas** — Checkout→Pedidos (ambos em `Compra`) e Promocoes→Catalogo
  (ambos em `Vitrine`) — logo **15 remotas**.
- O Checkout está em `Compra`; suas saídas remotas são Catalogo (Vitrine), Clientes (Identidade),
  Promocoes (Vitrine) e Pagamentos (Financeiro) = **4 diretas** (Pedidos é interna).
- Quanta com banco compartilhado = **1** (o banco liga tudo).
- Quanta com fila e banco por serviço = **2**: os 7 módulos exceto Comunicacao formam uma
  componente conexa (via chamadas síncronas restantes); Notificacoes fica isolada porque suas
  4 arestas de entrada viraram fila.

**Caso corrigido (item 2.3 do enunciado):** no `meu_quantum.py` inicial, eu havia definido
`diretas` como **arestas internas ao mesmo artefato** (o oposto da definição do enunciado: chamadas
**remotas** que saem da origem do fluxo) e `quanta_sincrono = total_artefatos` (um chute, não a
união-find do original). O sintoma foi o monólito aparecer com `diretas > 0`, o que é absurdo
(não há chamada remota dentro de um monólito). Corrigi reescrevendo `avaliar` com base no
`quantum.py` original: `diretas = chamadas_diretas_de(forma)` e `quanta` via DSU com os três
critérios (mesmo artefato, chamada síncrona, banco compartilhado).

**Saída do `pytest`:**
```
tests/test_meu_quantum.py::test_monolito PASSED [ 20%]
tests/test_meu_quantum.py::test_extracao_notificacoes PASSED [ 40%]
tests/test_meu_quantum.py::test_extracao_notificacoes_banco_por_servico PASSED [ 60%]
tests/test_meu_quantum.py::test_service_based PASSED [ 80%]
tests/test_meu_quantum.py::test_service_based_banco_por_servico_com_fila PASSED [100%]
================================ 5 passed in 0.04s ================================
```

### 2.4 `--assincronas`
python meu_quantum.py --assincronas "Pedidos>Notificacoes,Pagamentos>Notificacoes,Logistica>Notificacoes,Integracoes>Notificacoes" --banco-unico

text

**Resposta:** o menor conjunto que reduz os quanta **com banco por serviço** é o das **4 arestas
que chegam em Notificações** — Notificações se descola da componente conexa dos outros 7 módulos
(quanta vai de 1 para 2, o que é o **objetivo**: isolamento). **Com banco compartilhado, nenhum
conjunto basta**, porque o banco comum liga todos os componentes num único quantum,
independentemente de fila.

### 2.5 Tabela consolidada

| forma | artefatos | remotas | diretas | P(falha) | disponib. | min/mês | q_sync | q_fila |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| monólito modular | 1 | 0 | 0 | 0,0% | 99,9% | 43 | 1 | 1 |
| extração de Notificações | 2 | 4 | 0 | 0,0% | 99,8% | 86 | 1 | 1 |
| service-based (8) | 8 | 15 | 4 | 7,8% | 99,2% | 345 | 1 | 1 |
| microsserviços (10) | 10 | 17 | 5 | 9,6% | 99,0% | 432 | 1 | 1 |

*(P(falha) e disponib. calculados pelo script com `TAXA_DE_FALHA=0,02` e `DISPONIBILIDADE=0,999`.
A extração de Notificações tem **0 chamadas diretas do Checkout**, logo P(falha) do fechamento =
0 — o fechamento não paga latência extra por essa extração.)*

**Estruturais (lidos do grafo):** artefatos, arestas remotas, chamadas diretas, quanta.
**Hipótese:** P(falha) (depende de `TAXA_DE_FALHA`), disponibilidade e minutos/mês (dependem de
`DISPONIBILIDADE`).

---

## Parte 3 — Leitura

**Artigo escolhido: B — Designing robust and predictable APIs with idempotency (Stripe/Brandur Leach).**

**1. Tipos de falha e o "não sei se cobrou".** O texto distingue falhas em que a requisição
**nunca chegou** (seguro repetir) de falhas em que **chegou mas a resposta se perdeu** — esta é
exatamente o "cobrança indeterminada" da Aula 16. Quando a mesma chave chega de novo, o servidor
**não reexecuta o efeito**: devolve a resposta guardada da primeira execução.

**2. Chave e o que se guarda.** No artigo, **o cliente gera a chave** (UUID) e o servidor guarda
a chave + o resultado da operação. No Mini-Orion, `ChaveIdempotencia` guarda a chave, mas o
artigo vai além ao **guardar também a resposta** (status, corpo), permitindo devolver o mesmo
resultado sem reexecutar. O Mini-Orion foca em "não repetir o efeito"; o artigo foca em "não
repetir e devolver o mesmo resultado".

**3. Backoff com jitter.** O `ensaio.py` repete **imediatamente**. Se muitos clientes repetissem
ao mesmo tempo após uma falha comum, todos bateriam no servidor no mesmo instante (thundering
herd), agravando a falha. Com backoff exponencial + jitter, as repetições se espalham no tempo e
o servidor se recupera. No ensaio, isso **reduziria o pico de duplicadas** (menos tentativas
simultâneas) mas **não zeraria** — a idempotência continua sendo a única solução estrutural.

**Ligação com o cenário:** Notificações é o caso oposto ao de cobrança — repetir um e-mail é
indesejável mas tolerável; repetir uma cobrança é inaceitável. Por isso a política da Parte 1
para Notificações pode ser mais frouxa (fila + retry com backoff), enquanto Pagamentos exigiria
chave idempotente obrigatória.

---

## ADR — Extrair Notificações?

**Contexto.** Marketplace Orion, 10 componentes, 17 arestas. Candidato: Notificacoes, que recebe
de 4 componentes e cujas chamadas são efeitos de comunicação. Motivador: isolamento de falha +
assincronia natural (**alegado**, não medido). O fechamento da compra **não chama** Notificações
diretamente (0 chamadas diretas do Checkout).

**Decisão.** **Opção C** — extrair apenas Notificações, com as arestas de entrada por fila e
banco próprio para Notificações; o resto permanece como monólito modular.

**Alternativas.**
- **A — manter o monólito modular** (opção real): válida enquanto o volume de notificações não
  exigir escala independente nem isolamento de falha. **Gatilho de envelhecimento:** uma queda de
  Notificações derrubar o fechamento de compra, ou o time de comunicação precisar de cadência de
  release própria.
- **B — service-based por domínio (8 artefatos):** ganha fronteiras de domínio, mas paga 8
  artefatos e 15 arestas remotas sem resolver o problema específico de Notificações.
- **D — microsserviços (10 artefatos):** independência máxima, custo máximo — pior P(falha) e
  pior disponibilidade em série na tabela.

**Custo (números da tabela).** Extração de Notificações: **2 artefatos, 4 arestas remotas,
0 chamadas diretas do Checkout** — o fechamento da compra **não paga latência extra** por essa
extração. P(falha) e disponibilidade do fechamento **inalteradas**. Quanta: 1 com banco
compartilhado (fila não ajuda); 2 com banco por serviço + fila (Notificações se descola).
A política da Parte 1 acrescenta **estado para guardar chaves idempotentes** no consumidor da fila.

**Condição de falseamento.** Em 3 meses, se (a) a fila de Notificações não absorver picos sem
derrubar o fechamento, ou (b) o custo operacional de 2 artefatos + fila + banco próprio superar o
ganho de isolamento medido em incidentes, a decisão estava errada — voltar ao monólito (opção A).

**Como mediria.** Artefatos/remotas/diretas/quanta: **do código** (`meu_quantum.py`).
P(falha), disponibilidade, minutos/mês: **de produção** — medir taxa de erro por chamada remota,
SLO de cada artefato e incidentes que cruzaram a fronteira Notificações↔resto.