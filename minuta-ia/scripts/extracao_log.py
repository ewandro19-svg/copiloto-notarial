"""
Log real de cada chamada de extracao de IA -- quanto tempo levou, quantos
tokens de entrada/saida foram gastos, se deu certo ou estourou timeout/erro.

Antes disso nao existia nenhum registro real: so' estimativa. Isso serve
pra dois motivos:
  1. Medir de verdade quanto tempo/custo uma extracao leva (em vez de
     estimar), e comparar entre tipos de documento/modelo.
  2. Se travar de novo, da' pra abrir esse log e ver exatamente ONDE
     parou -- por tipo de documento, timestamp, e se foi timeout ou
     outro tipo de erro.

Usa o mesmo banco SQLite do historico.py/atividade.py (arquivo local
historico.db, tabela nova).

USO:
    from extracao_log import registrar_extracao, listar_extracoes_recentes

    inicio = time.time()
    try:
        resultado = extrair(...)
        registrar_extracao("imovel", modelo, tempo=time.time()-inicio,
                            input_tokens=X, output_tokens=Y, sucesso=True)
    except Exception as e:
        registrar_extracao("imovel", modelo, tempo=time.time()-inicio,
                            sucesso=False, erro=str(e))
"""
import sqlite3
import os
from datetime import datetime, timezone

# DADOS_DIR: quando definida (ex: "/var/data", apontando pro disco
# persistente da Render), os bancos SQLite vivem la' e sobrevivem a
# redeploy. Sem essa variavel (uso local, ou hospedagem sem disco
# persistente configurado), cai no comportamento antigo -- pasta raiz
# do projeto -- pra nao quebrar quem ja' roda local sem configurar nada.
_DIR_DADOS = os.environ.get("DADOS_DIR") or os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(_DIR_DADOS, "historico.db")


def _conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extracoes_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_documento TEXT NOT NULL,
            modelo TEXT,
            tempo_segundos REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_creation_tokens INTEGER,
            cache_read_tokens INTEGER,
            sucesso INTEGER NOT NULL,
            erro TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )
    # Migracao pra bancos ja existentes criados ANTES dessas 2 colunas
    # existirem -- sem isso, nao da' pra saber se o cache (item G do
    # ajuste de custo) esta' realmente funcionando: input_tokens sozinho
    # NAO mostra quanto foi escrita de cache (mais caro, 1.25x) vs
    # leitura de cache (mais barato, 10%) vs sem cache nenhum.
    for coluna in ("cache_creation_tokens", "cache_read_tokens"):
        try:
            conn.execute(f"ALTER TABLE extracoes_log ADD COLUMN {coluna} INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # coluna ja existe, banco criado depois dessa mudanca
    return conn


def registrar_extracao(
    tipo_documento: str,
    modelo: str | None,
    tempo_segundos: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    sucesso: bool = True,
    erro: str | None = None,
    cache_creation_tokens: int | None = None,
    cache_read_tokens: int | None = None,
) -> None:
    """Grava uma linha por chamada de extracao. Nunca deve derrubar o
    fluxo principal se falhar -- log e' coisa auxiliar, nao pode virar
    um novo motivo de erro pro usuario.

    cache_creation_tokens / cache_read_tokens: vem de
    usage.cache_creation_input_tokens / usage.cache_read_input_tokens da
    API -- sem isso, nao da' pra saber se o cache do documento (ajuste de
    custo G) esta' realmente sendo aproveitado numa chamada real, so'
    olhando input_tokens sozinho."""
    try:
        conn = _conectar()
        conn.execute(
            """INSERT INTO extracoes_log
               (tipo_documento, modelo, tempo_segundos, input_tokens,
                output_tokens, cache_creation_tokens, cache_read_tokens,
                sucesso, erro, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tipo_documento,
                modelo,
                round(tempo_segundos, 2),
                input_tokens,
                output_tokens,
                cache_creation_tokens,
                cache_read_tokens,
                1 if sucesso else 0,
                erro,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # log nunca pode quebrar o fluxo principal


def listar_extracoes_recentes(limite: int = 50) -> list[dict]:
    """Ultimas extracoes registradas -- util pra conferir tempo medio
    real e achar rapido se/onde algo travou ou deu erro."""
    conn = _conectar()
    linhas = conn.execute(
        """SELECT tipo_documento, modelo, tempo_segundos, input_tokens,
                  output_tokens, sucesso, erro, criado_em
           FROM extracoes_log ORDER BY criado_em DESC LIMIT ?""",
        (limite,),
    ).fetchall()
    conn.close()
    return [
        {
            "tipo_documento": t, "modelo": m, "tempo_segundos": s,
            "input_tokens": it, "output_tokens": ot,
            "sucesso": bool(suc), "erro": e, "criado_em": c,
        }
        for t, m, s, it, ot, suc, e, c in linhas
    ]


def tempo_medio_por_tipo() -> dict:
    """Tempo medio real (segundos) por tipo de documento, so' contando
    chamadas que tiveram sucesso -- usado pra substituir a estimativa
    por numero medido de verdade assim que houver dado suficiente."""
    conn = _conectar()
    linhas = conn.execute(
        """SELECT tipo_documento, AVG(tempo_segundos), COUNT(*)
           FROM extracoes_log WHERE sucesso = 1
           GROUP BY tipo_documento"""
    ).fetchall()
    conn.close()
    return {t: {"media_segundos": round(m, 1), "amostras": c} for t, m, c in linhas}
