import meu_quantum as q

def test_monolito():
    l = q.avaliar("monolito", q.forma_monolito(), banco_compartilhado=True)
    assert (l.artefatos, l.remotas, l.diretas) == (1, 0, 0)
    assert l.quanta_sincrono == 1
    assert l.quanta_com_fila == 1

def test_extracao_notificacoes():
    l = q.avaliar("extracao", q.forma_extracao_notificacoes(), banco_compartilhado=True)
    assert (l.artefatos, l.remotas, l.diretas) == (2, 4, 0)
    assert l.quanta_sincrono == 1     # banco comum ancora
    assert l.quanta_com_fila == 1

def test_extracao_notificacoes_banco_por_servico():
    l = q.avaliar("extracao", q.forma_extracao_notificacoes(), banco_compartilhado=False)
    assert l.quanta_sincrono == 1     # síncrono: Notificacoes ligada por chamada
    assert l.quanta_com_fila == 2     # fila descola Notificacoes

def test_service_based():
    l = q.avaliar("service-based", q.forma_service_based_por_dominio(), banco_compartilhado=True)
    assert (l.artefatos, l.remotas, l.diretas) == (8, 15, 4)
    assert l.quanta_sincrono == 1

def test_service_based_banco_por_servico_com_fila():
    l = q.avaliar("service-based", q.forma_service_based_por_dominio(), banco_compartilhado=False)
    assert l.quanta_com_fila == 2