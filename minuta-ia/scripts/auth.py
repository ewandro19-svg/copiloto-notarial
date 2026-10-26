"""
Autenticacao simples e real: usuarios ficam num banco SQLite local, senha
nunca fica em texto puro (hash com bcrypt). Sem auto-cadastro -- voce (admin)
cria cada usuario com o script criar_usuario.py, e so entrega login/senha pra
quem voce quer que teste.

Isso NAO e' um sistema de login enterprise (sem recuperacao de senha por
email, sem 2FA) -- mas e' autenticacao de verdade, nao gambiarra de senha
unica no codigo. Da pra evoluir depois se o produto crescer.
"""
import sqlite3
import bcrypt
import os

# DADOS_DIR: quando definida (ex: "/var/data", apontando pro disco
# persistente da Render), os bancos SQLite vivem la' e sobrevivem a
# redeploy. Sem essa variavel (uso local, ou hospedagem sem disco
# persistente configurado), cai no comportamento antigo -- pasta raiz
# do projeto -- pra nao quebrar quem ja' roda local sem configurar nada.
_DIR_DADOS = os.environ.get("DADOS_DIR") or os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(_DIR_DADOS, "usuarios.db")


def _conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            senha_hash BLOB NOT NULL,
            nome_completo TEXT,
            cartorio TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Migracao pra bancos ja existentes criados ANTES da coluna is_admin
    # existir -- ALTER TABLE falha silenciosamente se a coluna ja' existe
    # (SQLite nao tem "ADD COLUMN IF NOT EXISTS").
    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # coluna ja existe, banco criado depois dessa mudanca
    return conn


def criar_usuario(username: str, senha: str, nome_completo: str = "", cartorio: str = "", is_admin: bool = False):
    conn = _conectar()
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt())
    try:
        conn.execute(
            "INSERT INTO usuarios (username, senha_hash, nome_completo, cartorio, is_admin) VALUES (?, ?, ?, ?, ?)",
            (username, senha_hash, nome_completo, cartorio, 1 if is_admin else 0),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # username ja existe
    finally:
        conn.close()


def verificar_login(username: str, senha: str) -> dict | None:
    """Retorna os dados do usuario se a senha bater, ou None se falhar."""
    conn = _conectar()
    row = conn.execute(
        "SELECT username, senha_hash, nome_completo, cartorio, is_admin FROM usuarios WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    if row is None:
        return None

    username_db, senha_hash, nome_completo, cartorio, is_admin = row
    if bcrypt.checkpw(senha.encode("utf-8"), senha_hash):
        return {
            "username": username_db,
            "nome_completo": nome_completo,
            "cartorio": cartorio,
            "is_admin": bool(is_admin),
        }
    return None


def listar_usuarios():
    conn = _conectar()
    rows = conn.execute(
        "SELECT username, nome_completo, cartorio, criado_em, is_admin FROM usuarios"
    ).fetchall()
    conn.close()
    return rows


def existe_algum_usuario() -> bool:
    """Usado so' na inicializacao do sistema, pra decidir se o PRIMEIRO
    usuario criado (bootstrap) deve nascer admin -- ninguem mais depois
    dele nasce admin automaticamente."""
    conn = _conectar()
    row = conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
    conn.close()
    return row is not None


def remover_usuario(username: str) -> bool:
    """Remove um usuario pelo username. Retorna True se removeu de fato
    (existia), False se o username nao existia -- usado pra tela de
    Configuracoes > Usuarios ter um botao real de exclusao, em vez de
    contas ficarem acumuladas pra sempre (ex: a conta 'joao'/'João Silva'
    criada a partir do EXEMPLO do docstring de criar_usuario.py, copiado e
    colado literalmente em vez de substituido pelos dados reais)."""
    conn = _conectar()
    cursor = conn.execute("DELETE FROM usuarios WHERE username = ?", (username,))
    conn.commit()
    removeu = cursor.rowcount > 0
    conn.close()
    return removeu
