"""
Historico de partes (outorgantes/outorgados) ja usadas em minutas
anteriores -- permite buscar por CPF/CNPJ e reaproveitar os dados sem
precisar re-subir e re-processar o mesmo documento de um cliente
recorrente.

Usa SQLite, mesmo padrao do auth.py (arquivo local, sem servidor externo).

USO:
    from historico import salvar_parte, buscar_por_documento, listar_recentes

    salvar_parte({"nome": "José da Silva", "cpf": "111.444.777-35", ...})
    dados = buscar_por_documento("111.444.777-35")
"""
import sqlite3
import json
import os
import re
from datetime import datetime

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
        CREATE TABLE IF NOT EXISTS partes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT NOT NULL,
            nome TEXT,
            tipo TEXT,
            dados_json TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_partes_documento ON partes(documento)")
    return conn


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def salvar_parte(dados: dict) -> None:
    """Salva (ou atualiza, se o documento ja existir) os dados de uma
    parte. 'dados' e' o dict que ja vem da extracao (pessoa ou
    pessoa_juridica) -- precisa ter 'cpf' ou 'cnpj' preenchido, senao
    nao ha como buscar depois."""
    documento = _so_digitos(dados.get("cpf") or dados.get("cnpj") or "")
    if not documento:
        return  # sem documento nao da pra indexar, nao salva

    nome = dados.get("nome") or dados.get("razao_social") or ""
    tipo = dados.get("_tipo", "PF")

    conn = _conectar()
    existente = conn.execute(
        "SELECT id FROM partes WHERE documento = ?", (documento,)
    ).fetchone()

    agora = datetime.now().isoformat(timespec="seconds")
    dados_limpos = {k: v for k, v in dados.items() if not k.startswith("_")}
    dados_json = json.dumps(dados_limpos, ensure_ascii=False)

    if existente:
        conn.execute(
            "UPDATE partes SET nome=?, tipo=?, dados_json=?, atualizado_em=? WHERE documento=?",
            (nome, tipo, dados_json, agora, documento),
        )
    else:
        conn.execute(
            "INSERT INTO partes (documento, nome, tipo, dados_json, atualizado_em) VALUES (?,?,?,?,?)",
            (documento, nome, tipo, dados_json, agora),
        )
    conn.commit()
    conn.close()


def buscar_por_documento(cpf_ou_cnpj: str) -> dict | None:
    """Busca uma parte pelo CPF/CNPJ (aceita com ou sem formatacao).
    Retorna o dict de dados salvo da ultima vez, ou None se nao achar."""
    documento = _so_digitos(cpf_ou_cnpj)
    if not documento:
        return None

    conn = _conectar()
    linha = conn.execute(
        "SELECT dados_json, tipo, atualizado_em FROM partes WHERE documento = ?", (documento,)
    ).fetchone()
    conn.close()

    if not linha:
        return None

    dados = json.loads(linha[0])
    dados["_tipo"] = linha[1]
    dados["_atualizado_em"] = linha[2]
    return dados


def listar_recentes(limite: int = 20) -> list[dict]:
    """Lista as partes mais recentemente usadas/atualizadas, pra mostrar
    tipo um autocomplete/atalho na tela de novo documento."""
    conn = _conectar()
    linhas = conn.execute(
        "SELECT documento, nome, tipo, atualizado_em FROM partes ORDER BY atualizado_em DESC LIMIT ?",
        (limite,),
    ).fetchall()
    conn.close()
    return [
        {"documento": d, "nome": n, "tipo": t, "atualizado_em": a}
        for d, n, t, a in linhas
    ]
