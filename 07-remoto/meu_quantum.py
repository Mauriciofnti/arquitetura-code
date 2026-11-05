"""O quantum do Orion adaptado: extração de Notificacoes (projeto Aulas 16/17).

Uso:
    python meu_quantum.py
    python meu_quantum.py --notificacoes-assincronas
    python meu_quantum.py --banco-unico
    python meu_quantum.py --assincronas "Pedidos>Notificacoes,Pagamentos>Notificacoes"
"""

import argparse
from dataclasses import dataclass

ARESTAS: list[tuple[str, str]] = [
    ("Portal", "Catalogo"), ("Portal", "Checkout"), ("Portal", "Pedidos"),
    ("Portal", "Clientes"),
    ("Checkout", "Catalogo"), ("Checkout", "Clientes"), ("Checkout", "Promocoes"),
    ("Checkout", "Pagamentos"), ("Checkout", "Pedidos"),
    ("Promocoes", "Catalogo"),
    ("Pedidos", "Notificacoes"), ("Pedidos", "Logistica"),
    ("Pagamentos", "Notificacoes"),
    ("Logistica", "Notificacoes"),
    ("Integracoes", "Catalogo"), ("Integracoes", "Pedidos"), ("Integracoes", "Notificacoes"),
]

COMPONENTES = sorted({c for a in ARESTAS for c in a})

ORIGEM_DO_FLUXO = "Checkout"
DESTINO_DA_FILA = "Notificacoes"

MODULOS: dict[str, list[str]] = {
    "Borda": ["Portal"],
    "Vitrine": ["Catalogo", "Promocoes"],
    "Compra": ["Checkout", "Pedidos"],
    "Financeiro": ["Pagamentos"],
    "Distribuicao": ["Logistica"],
    "Comunicacao": ["Notificacoes"],
    "Identidade": ["Clientes"],
    "Integracao": ["Integracoes"],
}

TAXA_DE_FALHA = 0.02
DISPONIBILIDADE = 0.999
MINUTOS_NO_MES = 30 * 24 * 60

Forma = dict[str, str]


# ---------- formas ----------
def forma_monolito() -> Forma:
    return {c: "orion" for c in COMPONENTES}


def forma_extracao_notificacoes() -> Forma:
    """Candidato: Notificacoes num artefato; o resto no monólito modular."""
    return {c: ("notificacoes" if c == DESTINO_DA_FILA else "orion") for c in COMPONENTES}


def forma_service_based_por_dominio() -> Forma:
    """Os oito módulos de domínio da Aula 12 -> oito artefatos."""
    return {c: modulo for modulo, itens in MODULOS.items() for c in itens}


def forma_microsservicos() -> Forma:
    return {c: c for c in COMPONENTES}


# ---------- conta ----------
def arestas_remotas(forma: Forma) -> list[tuple[str, str]]:
    return [(a, b) for a, b in ARESTAS if forma[a] != forma[b]]


def chamadas_diretas_de(forma: Forma, origem: str = ORIGEM_DO_FLUXO) -> int:
    return sum(1 for a, b in arestas_remotas(forma) if a == origem)


def artefatos_do_fechamento(forma: Forma, origem: str = ORIGEM_DO_FLUXO) -> int:
    tocados = {forma[origem]} | {forma[b] for a, b in ARESTAS if a == origem}
    return len(tocados)


def quanta(
    forma: Forma,
    assincronas: set[tuple[str, str]] | None = None,
    banco_compartilhado: bool = True,
) -> int:
    assincronas = assincronas or set()
    pai = {c: c for c in COMPONENTES}

    def raiz(c: str) -> str:
        while pai[c] != c:
            pai[c] = pai[pai[c]]
            c = pai[c]
        return c

    ligacoes = [(a, b) for a in COMPONENTES for b in COMPONENTES if forma[a] == forma[b]]
    ligacoes += [aresta for aresta in ARESTAS if aresta not in assincronas]
    if banco_compartilhado:
        ligacoes += [(COMPONENTES[0], c) for c in COMPONENTES[1:]]
    for a, b in ligacoes:
        pai[raiz(a)] = raiz(b)
    return len({raiz(c) for c in COMPONENTES})


def notificacoes_assincronas() -> set[tuple[str, str]]:
    return {(a, b) for a, b in ARESTAS if b == DESTINO_DA_FILA}


def p_ao_menos_uma_falha(chamadas: int, taxa: float = TAXA_DE_FALHA) -> float:
    return 1 - (1 - taxa) ** chamadas


def disponibilidade_em_serie(artefatos: int, base: float = DISPONIBILIDADE) -> float:
    return base**artefatos


@dataclass
class Linha:
    nome: str
    artefatos: int
    remotas: int
    diretas: int
    p_falha: float
    disponibilidade: float
    minutos: float
    quanta_sincrono: int
    quanta_com_fila: int


def avaliar(
    nome: str,
    forma: Forma,
    banco_compartilhado: bool = True,
    assincronas: set[tuple[str, str]] | None = None,
) -> Linha:
    tocados = artefatos_do_fechamento(forma)
    diretas = chamadas_diretas_de(forma)
    disp = disponibilidade_em_serie(tocados)
    if assincronas is None:
        assincronas = notificacoes_assincronas()
    return Linha(
        nome=nome,
        artefatos=len(set(forma.values())),
        remotas=len(arestas_remotas(forma)),
        diretas=diretas,
        p_falha=p_ao_menos_uma_falha(diretas),
        disponibilidade=disp,
        minutos=(1 - disp) * MINUTOS_NO_MES,
        quanta_sincrono=quanta(forma, banco_compartilhado=banco_compartilhado),
        quanta_com_fila=quanta(forma, assincronas, banco_compartilhado),
    )


def pct(x: float) -> str:
    return f"{100 * x:.1f}%".replace(".", ",")


def imprimir(linhas: list[Linha]) -> None:
    print(f"Grafo: {len(COMPONENTES)} componentes, {len(ARESTAS)} arestas.\n")
    print(f"{'forma':30}{'art':>5}{'rem':>5}{'dir':>5}{'P(falha)':>10}"
          f"{'disp':>8}{'min/mes':>9}{'q_sync':>7}{'q_fila':>7}")
    for x in linhas:
        print(f"{x.nome:30}{x.artefatos:5d}{x.remotas:5d}{x.diretas:5d}"
              f"{pct(x.p_falha):>10}{pct(x.disponibilidade):>8}{x.minutos:9.0f}"
              f"{x.quanta_sincrono:7d}{x.quanta_com_fila:7d}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--notificacoes-assincronas", action="store_true")
    ap.add_argument("--banco-unico", action="store_true")
    ap.add_argument("--assincronas", help='ex.: "Pedidos>Notificacoes,Pagamentos>Notificacoes"')
    args = ap.parse_args()

    if args.assincronas:
        assinc = set()
        for par in args.assincronas.split(","):
            par = par.strip()
            if not par:
                continue
            a, b = par.split(">")
            assinc.add((a.strip(), b.strip()))
    else:
        assinc = notificacoes_assincronas()
    
    formas = [
        ("monolito modular", forma_monolito(), True),
        ("extracao de Notificacoes", forma_extracao_notificacoes(), True),
        ("service-based (8 dominios)", forma_service_based_por_dominio(), True),
        ("microsservicos (10)", forma_microsservicos(), args.banco_unico),
    ]
    imprimir([avaliar(n, f, banco or args.banco_unico, assinc) for n, f, banco in formas])


if __name__ == "__main__":
    main()