"""
Voce (admin) roda este script pra criar login de quem vai testar o sistema.
Nao ha auto-cadastro -- e' proposital, pra voce controlar quem tem acesso.

USO:
    python3 scripts/criar_usuario.py
    (vai perguntar username, senha, nome e cartorio interativamente)

    ou direto:
    python3 scripts/criar_usuario.py --username joao --senha "SenhaForte123" --nome "João Silva" --cartorio "2º Tabelionato de X"
"""
import argparse
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from auth import criar_usuario, listar_usuarios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username")
    ap.add_argument("--senha")
    ap.add_argument("--nome", default="")
    ap.add_argument("--cartorio", default="")
    ap.add_argument("--listar", action="store_true", help="so lista os usuarios existentes")
    args = ap.parse_args()

    if args.listar:
        print("Usuários cadastrados:")
        for u in listar_usuarios():
            print(f"  - {u[0]} | {u[1]} | {u[2]} | criado em {u[3]}")
        return

    username = args.username or input("Username (sem espaço, ex: joao.silva): ").strip()
    senha = args.senha or getpass.getpass("Senha: ")
    nome = args.nome or input("Nome completo: ").strip()
    cartorio = args.cartorio or input("Cartório/Tabelionato: ").strip()

    if len(senha) < 8:
        print("Senha precisa ter pelo menos 8 caracteres.")
        return

    ok = criar_usuario(username, senha, nome, cartorio)
    if ok:
        print(f"Usuário '{username}' criado com sucesso.")
    else:
        print(f"Erro: username '{username}' já existe.")


if __name__ == "__main__":
    main()
