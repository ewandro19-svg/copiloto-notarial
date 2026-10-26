"""
Validacoes deterministicas (sem IA) -- digito verificador de CPF/CNPJ e
conversao de valor numerico para extenso.

Por que isso nao usa IA: sao calculos matematicos fixos, ja definidos por
lei (CPF: Instrucao Normativa RFB, CNPJ: mesma logica de modulo 11). Rodar
isso em codigo puro e' mais rapido, mais barato (zero chamada de API) e
100% confiavel -- ao contrario de extracao de documento, aqui nao ha
ambiguidade nenhuma a resolver.

USO:
    from validadores import validar_cpf, validar_cnpj, valor_por_extenso
    validar_cpf("123.456.789-00")  -> False (digito nao bate)
    valor_por_extenso(450000.00)   -> "quatrocentos e cinquenta mil reais"
"""
import re


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_cpf(cpf: str) -> bool:
    """Retorna True se o CPF tem digito verificador valido.
    Nao verifica se o CPF existe/esta ativo na Receita -- so a matematica."""
    cpf = _so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    d1 = 0 if resto == 10 else resto
    if d1 != int(cpf[9]):
        return False

    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    d2 = 0 if resto == 10 else resto
    return d2 == int(cpf[10])


def validar_cnpj(cnpj: str) -> bool:
    """Retorna True se o CNPJ tem digito verificador valido."""
    cnpj = _so_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
    resto = soma % 11
    d1 = 0 if resto < 2 else 11 - resto
    if d1 != int(cnpj[12]):
        return False

    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
    resto = soma % 11
    d2 = 0 if resto < 2 else 11 - resto
    return d2 == int(cnpj[13])


# ---------------------------------------------------------------------------
# Valor por extenso (reais e centavos), sem depender de biblioteca externa
# ---------------------------------------------------------------------------
_UNIDADES = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
_DEZ_A_DEZENOVE = ["dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
                    "dezessete", "dezoito", "dezenove"]
_DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
            "oitenta", "noventa"]
_CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
             "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _grupo_por_extenso(n: int) -> str:
    """Converte um numero de 0 a 999 por extenso."""
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    partes = []
    c, resto = divmod(n, 100)
    if c:
        partes.append(_CENTENAS[c])
    if resto >= 20:
        d, u = divmod(resto, 10)
        txt = _DEZENAS[d]
        if u:
            txt += " e " + _UNIDADES[u]
        partes.append(txt)
    elif resto >= 10:
        partes.append(_DEZ_A_DEZENOVE[resto - 10])
    elif resto > 0:
        partes.append(_UNIDADES[resto])
    return " e ".join(partes)


def _inteiro_por_extenso(n: int) -> str:
    if n == 0:
        return "zero"

    ESCALAS = [
        (1_000_000_000, "bilhão", "bilhões"),
        (1_000_000, "milhão", "milhões"),
        (1_000, "mil", "mil"),
    ]

    partes = []
    resto = n
    for valor, sing, plur in ESCALAS:
        if resto >= valor:
            qtd, resto = divmod(resto, valor)
            if valor == 1_000 and qtd == 1:
                partes.append("mil")
            else:
                nome = sing if qtd == 1 else plur
                partes.append(f"{_grupo_por_extenso(qtd)} {nome}")

    if resto > 0:
        partes.append(_grupo_por_extenso(resto))

    # "e" antes do ultimo grupo quando o resto final e' < 100 (regra comum
    # de portugues numerico: "mil e cem", "dois milhões e um")
    if len(partes) > 1 and resto > 0 and resto < 100:
        return ", ".join(partes[:-1]) + " e " + partes[-1]
    return ", ".join(partes)


def _termina_em_escala_redonda(texto: str) -> bool:
    """True se o numero por extenso termina exatamente em milhao(oes)/bilhao(oes)
    sem resto -- caso em que a gramatica exige 'de' antes do substantivo
    seguinte (ex: 'um milhão de reais', nunca 'um milhão reais')."""
    return texto.split(" ")[-1] in ("milhão", "milhões", "bilhão", "bilhões")


def valor_por_extenso(valor) -> str:
    """Converte um valor monetario (float, int, ou string tipo '450.000,00')
    para texto por extenso em reais. Usado no item 9 da minuta (forma de
    pagamento), pra nao depender de digitacao manual duplicada."""
    if isinstance(valor, str):
        limpo = valor.replace(".", "").replace(",", ".")
        limpo = re.sub(r"[^\d.]", "", limpo)
        valor = float(limpo) if limpo else 0.0

    reais = int(valor)
    centavos = round((valor - reais) * 100)

    partes = []
    if reais > 0:
        extenso_reais = _inteiro_por_extenso(reais)
        nome_reais = "real" if reais == 1 else "reais"
        conector = "de " if _termina_em_escala_redonda(extenso_reais) else ""
        partes.append(f"{extenso_reais} {conector}{nome_reais}")
    if centavos > 0:
        extenso_centavos = _inteiro_por_extenso(centavos)
        nome_centavos = "centavo" if centavos == 1 else "centavos"
        partes.append(f"{extenso_centavos} {nome_centavos}")

    if not partes:
        return "zero reais"
    return " e ".join(partes)
