"""
Registro de atividade -- cada vez que uma minuta e' gerada de verdade,
fica salvo aqui. E' o que alimenta o dashboard (Area de trabalho) com
numero real de minutas geradas e a tabela de atividade recente, em vez
de dado de exemplo fixo.

Usa o mesmo banco SQLite do historico.py (mesmo arquivo, tabela nova).
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
        CREATE TABLE IF NOT EXISTS minutas_geradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_ato TEXT,
            outorgante_nome TEXT,
            outorgado_nome TEXT,
            gerada_em TEXT NOT NULL
        )
        """
    )
    return conn


def registrar_minuta(tipo_ato: str, outorgante_nome: str, outorgado_nome: str) -> None:
    conn = _conectar()
    conn.execute(
        "INSERT INTO minutas_geradas (tipo_ato, outorgante_nome, outorgado_nome, gerada_em) VALUES (?, ?, ?, ?)",
        (tipo_ato, outorgante_nome, outorgado_nome, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def contar_minutas_mes() -> int:
    """Conta quantas minutas foram geradas no mes corrente (UTC)."""
    conn = _conectar()
    mes_atual = datetime.now(timezone.utc).strftime("%Y-%m")
    row = conn.execute(
        "SELECT COUNT(*) FROM minutas_geradas WHERE gerada_em LIKE ?",
        (mes_atual + "%",),
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def contar_minutas_total() -> int:
    conn = _conectar()
    row = conn.execute("SELECT COUNT(*) FROM minutas_geradas").fetchone()
    conn.close()
    return row[0] if row else 0


def listar_atividade_recente(limite: int = 10) -> list[dict]:
    conn = _conectar()
    rows = conn.execute(
        "SELECT tipo_ato, outorgante_nome, outorgado_nome, gerada_em FROM minutas_geradas ORDER BY gerada_em DESC LIMIT ?",
        (limite,),
    ).fetchall()
    conn.close()
    return [
        {"tipo_ato": t, "outorgante_nome": o1, "outorgado_nome": o2, "gerada_em": g}
        for t, o1, o2, g in rows
    ]
