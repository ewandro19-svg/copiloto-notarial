"""
Perfil do cartorio -- dados fixos (nome do tabeliao, cargo, numero do
tabelionato, cidade, comarca) que alimentam AUTOMATICAMENTE o preambulo
de toda minuta gerada, sem precisar digitar de novo a cada caso.

Isso e' o que a secao "Perfil e Cartorio" (Configuracoes) promete desde o
inicio do projeto -- so' que agora conectado de verdade.
"""
import json
import os

CAMINHO_PERFIL = os.path.join(os.path.dirname(__file__), "..", "dados", "perfil.json")

PERFIL_PADRAO = {
    "tabeliao_nome": "",
    "tabeliao_cargo": "Tabeliã(o) de Notas",
    "cartorio_nome": "",
    "cartorio_numero": "",
    "cartorio_cidade": "Curitiba",
    "cartorio_uf_extenso": "Capital do Estado do Paraná",
    "comarca": "Curitiba",
    "cns": "",
}


def carregar_perfil() -> dict:
    if not os.path.exists(CAMINHO_PERFIL):
        return dict(PERFIL_PADRAO)
    with open(CAMINHO_PERFIL, "r", encoding="utf-8") as f:
        dados = json.load(f)
    perfil = dict(PERFIL_PADRAO)
    perfil.update(dados)
    return perfil


def salvar_perfil(dados: dict) -> None:
    perfil = carregar_perfil()
    perfil.update({k: v for k, v in dados.items() if k in PERFIL_PADRAO})
    os.makedirs(os.path.dirname(CAMINHO_PERFIL), exist_ok=True)
    with open(CAMINHO_PERFIL, "w", encoding="utf-8") as f:
        json.dump(perfil, f, ensure_ascii=False, indent=2)
