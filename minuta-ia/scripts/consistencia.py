"""
Checagens de consistencia CRUZADA entre documentos ja extraidos -- nao
extrai nada novo, so compara o que ja veio de fontes diferentes (RG,
matricula, certidao de casamento, comprovante de residencia, procuracao)
e aponta divergencia. Isso e' logica pura (normalizacao de string +
comparacao), sem chamada de IA -- os dados ja foram extraidos antes.

USO:
    from consistencia import checar_divergencia_nomes
    checar_divergencia_nomes({
        "RG": "José da Silva",
        "Matrícula": "José Maria da Silva",
        "Certidão de Casamento": "José da Silva",
    })
    -> ["Nome diverge entre RG ('José da Silva') e Matrícula ('José Maria da Silva')."]
"""
import re
import unicodedata


def _normalizar(nome: str) -> str:
    """Deixa o nome comparavel: sem acento, minusculo, sem espaco duplo."""
    if not nome:
        return ""
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"\s+", " ", nome).strip().lower()
    return nome


def _nomes_batem(a: str, b: str) -> bool:
    """Compara dois nomes de forma tolerante: identico, ou um e' um
    subconjunto de palavras do outro (cobre abreviacao de nome do meio,
    tipo 'José da Silva' vs 'José Maria da Silva' -- isso ainda ASSIM
    fica marcado como divergencia pelo criterio mais estrito abaixo,
    porque a diferenca de nome do meio e' justamente o tipo de coisa que
    o escrevente precisa conferir, nao ignorar)."""
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return True  # nao da pra comparar, nao acusa falso alarme
    return na == nb


def checar_divergencia_nomes(nomes_por_fonte: dict) -> list[str]:
    """Recebe um dict {"nome da fonte": "nome extraido"} e compara todos
    os pares. Retorna lista de alertas em texto pronto pra exibir como
    ponto de atencao. Fontes com nome vazio/None sao ignoradas (documento
    nao apresentado ou sem nome legivel)."""
    fontes = [(f, n) for f, n in nomes_por_fonte.items() if n]
    alertas = []
    for i in range(len(fontes)):
        for j in range(i + 1, len(fontes)):
            fonte_a, nome_a = fontes[i]
            fonte_b, nome_b = fontes[j]
            if not _nomes_batem(nome_a, nome_b):
                alertas.append(
                    f"Nome diverge entre {fonte_a} ('{nome_a}') e {fonte_b} ('{nome_b}')."
                )
    return alertas


def checar_divergencia_pessoa(dados_pessoa: dict, dados_imovel: dict | None = None,
                               dados_procuracao: dict | None = None) -> list[str]:
    """Atalho pro caso mais comum do fluxo: comparar o nome extraido do
    RG/CPF de uma parte com o nome do proprietario na matricula (se essa
    parte for outorgante) e com o nome do outorgante na procuracao (se
    houver representacao por procurador)."""
    nomes = {"Documento de identificação": dados_pessoa.get("nome")}
    if dados_imovel:
        nomes["Matrícula"] = dados_imovel.get("proprietario_atual")
    if dados_procuracao:
        nomes["Procuração"] = dados_procuracao.get("nome_outorgante")
    return checar_divergencia_nomes(nomes)
