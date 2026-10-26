"""
Preenche um modelo de minuta em .docx enviado pelo proprio usuario --
le as tags «» diretamente do arquivo Word (RUN por RUN, preservando
negrito/italico/etc de verdade, porque agora e' um .docx de verdade, nao
texto colado), sem precisar converter nada em JSON/item por minuta.

Isso e' DIFERENTE do motor_minuta.py (que monta a partir de itens
cadastrados no dados/itens_minuta.json). Esse arquivo aqui serve pra
quando o usuario quer subir o proprio .docx pronto e so' ter as tags
preenchidas -- sem cadastrar item nenhum antes.

Três categorias de tag, todas escritas como «conteudo» dentro do proprio
Word:

  1. CONCORDANCIA -- «palavra:grupo» (ex: «VENDEDOR:1», «IMÓVEL:4») --
     resolvida usando concordancia.py, exatamente como no motor_minuta.

  2. VARIAVEL -- qualquer outra coisa dentro de «» (ex: «NomeOutorgante»,
     «<NUMERO_MATRICULA>», «<QUALIFICAR_OUTORGANTE>») -- resolvida
     olhando REGISTRO_VARIAVEIS (cadastro fixo, uma vez so') e rodando o
     "motorzinho" de substituicao {{ }} do motor_minuta.py em cima do
     "molde" cadastrado pra aquela variavel.

  3. CERTIDAO -- «CERTIDAO:tipo_id» (ou «CERTIDAO:lado:tipo_id», com
     lado = 'outorgante' ou 'outorgado', default 'outorgante') marca um
     PARAGRAFO inteiro como sendo sobre uma certidao especifica. Dentro
     do MESMO paragrafo, as tags «<CERT_NUMERO>», «<CERT_DATA_EMISSAO>»,
     «<CERT_DATA_VALIDADE>» e «<CERT_SITUACAO>» sao resolvidas com o dado
     daquela certidao. Se a certidao NAO foi enviada pela pessoa, todo o
     texto do paragrafo DEPOIS da marca «CERTIDAO:...» e' substituido por
     uma frase padrao de dispensa -- a letra/numeracao que vier ANTES da
     marca (ex: 'b)') fica exatamente como estava, pra nao precisar de
     renumeracao. Se a certidao vier com situacao 'positiva' (nao
     'negativa' nem 'positiva com efeito de negativa'), isso gera um
     ALERTA CRITICO separado (retornado por processar_docx), pra chamar
     atencao do tabeliao antes de prosseguir -- o texto ainda e'
     preenchido normalmente, so' o alerta que aparece a parte.

Se aparecer uma variavel ou palavra de concordancia NUNCA vista antes
(nao cadastrada em nenhuma das tabelas), o texto original da tag fica
visivel no documento final (nao trava, nao inventa valor) e sai um
aviso -- assim da' pra saber exatamente o que falta cadastrar, sem
arriscar um valor errado numa escritura de verdade.

USO:
    from minuta_docx_resolver import processar_docx
    resultado = processar_docx("caminho/entrada.docx", "caminho/saida.docx",
                                contexto, condicoes)
    # resultado e' um dict: {"avisos": [...], "alertas_criticos": [...]}
"""
import re

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from concordancia import (
    PALAVRAS_PESSOA, PALAVRAS_NUMERO_FIXO,
    calcular_concordancia_grupo, calcular_concordancia_quantidade,
    enriquecer_pessoa_com_concordancia,
)
from motor_minuta import _substituir_variaveis
from extrair_dados import TIPOS_CERTIDAO, CERTIDOES_DISPENSAVEIS_POR_DECLARACAO

_NOMES_LEGIVEIS_CERTIDAO = dict(TIPOS_CERTIDAO)
_NOMES_LEGIVEIS_CERTIDAO["feitos_comarca_diferente"] = "Feitos Ajuizados — comarca diferente"
_NOMES_LEGIVEIS_CERTIDAO["tributos_municipais"] = "Certidão de Tributos Municipais"


def _texto_dispensa_certidao(tipo_id: str) -> str:
    """Frase padrao de dispensa -- mesma estrutura acordada com o usuario:
    base legal + assuncao de responsabilidade pelas partes + isencao do
    tabelionato. O nome da certidao entra automaticamente.

    So' usada pras 3 certidoes que ADMITEM dispensa por declaracao (ver
    CERTIDOES_DISPENSAVEIS_POR_DECLARACAO em extrair_dados.py). Chamar
    isso pra uma das 4 obrigatorias seria escrever uma dispensa que a
    lei/norma nao permite -- por isso ha' uma checagem separada em
    _processar_paragrafo_certidao que decide qual das duas frases usar."""
    nome = _NOMES_LEGIVEIS_CERTIDAO.get(tipo_id, tipo_id)
    return (
        f"as partes, cientes dos riscos decorrentes, dispensam expressamente a apresentação "
        f"da {nome}, assumindo toda e qualquer responsabilidade civil e/ou penal por eventuais "
        f"prejuízos que a ausência desse documento venha a acarretar, isentando este "
        f"Tabelionato de qualquer responsabilidade a respeito, nos termos do Decreto-Lei "
        f"nº 93.240/86 e do Código de Normas da Corregedoria-Geral da Justiça."
    )


def _texto_certidao_obrigatoria_pendente(tipo_id: str) -> str:
    """Marcacao visivel pra uma das 4 certidoes OBRIGATORIAS quando ela
    nao foi apresentada -- nunca deve virar uma dispensa silenciosa, tem
    que aparecer destacado no documento (pro tabeliao ver na hora de
    revisar antes de assinar) e tambem sobe como alerta_critico."""
    nome = _NOMES_LEGIVEIS_CERTIDAO.get(tipo_id, tipo_id)
    return f"[PENDENTE: {nome} não apresentada — documento obrigatório, sem dispensa possível]"


_SITUACAO_LEGIVEL = {
    "negativa": "Negativa",
    "positiva": "Positiva",
    "positiva com efeito de negativa": "Positiva com Efeito de Negativa",
}


# ---------------------------------------------------------------------------
# CADASTRO DE VARIAVEIS -- uma vez so' aqui, serve pra QUALQUER minuta que
# use esses mesmos nomes de tag daqui em diante (doacao, inventario, etc.),
# sem precisar de nenhum trabalho novo. So' cresce quando aparecer uma
# variavel de verdade nova (nao cadastrada ainda).
#
# Cada valor e' um "molde" na sintaxe {{ }} que o motor_minuta.py ja' sabe
# resolver (inclusive {{#lista}}...{{/lista}} pra repetir por pessoa).
# ---------------------------------------------------------------------------
REGISTRO_VARIAVEIS = {
    "NOMEOUTORGANTE": "{{#outorgantes}}" + "{{nome}}" + "{{/outorgantes}}",
    "NOMEOUTORGADO": "{{#outorgados}}" + "{{nome}}" + "{{/outorgados}}",
    "NOME CONJUGE OUTORGANTE": "{{conjuge_outorgante_texto}}",
    "ORDEM DE LAVRATURA": "{{ordem_lavratura}}",
    "DATA DE LAVRATURA": "{{data_lavratura}}",
    "QUALIFICAR_OUTORGANTE": "{{#outorgantes}}" + "{{texto_qualificacao}}" + "{{/outorgantes}}",
    "QUALIFICAR_OUTORGADOS": "{{#outorgados}}" + "{{texto_qualificacao}}" + "{{/outorgados}}",
    "DESCRICAO_DO_IMOVEL": "{{imovel.descricao}}",
    "NUMERO_MATRICULA": "{{imovel.matricula}}",
    "NÚMERO MATRICULA": "{{imovel.matricula}}",
    "CIRCUNSCRICAO_E_COMARCA": "{{imovel.circunscricao}} Circunscrição da Comarca de {{imovel.comarca}}",
    "TITULO_AQUISITIVO": "{{imovel.titulo_aquisitivo}}",
    "INDICACAO_FISCAL": "{{imovel.indicacao_fiscal}}",
    "VALOR": "{{valor}}",
    "FRACAO_VENDIDA": "{{fracao_vendida}}",
    "FORMA_DE_PAGAMENTO": "{{forma_pagamento}}",
    "CITAR_ONUS_(SE_HOUVER)": "{{onus_citacao}}",
    "SITUACAO_ONUS_PROPRIEDADE": "{{situacao_onus_imovel}}",
    "DATA_CERTIDAO_MATRICULA": "{{imovel.data_emissao_certidao}}",
    "PARTE_IDEAL": "{{parte_ideal_texto}}",

    # -- aliases -- os mesmos dados de cima, mas sob os nomes alternativos
    # que apareceram de verdade nos 7 modelos de referencia (Doacao, Dacao
    # em Pagamento etc.) -- cada escrevente que fez o rascunho usou uma
    # variacao ligeiramente diferente do nome (com/sem acento, com/sem
    # "DO", espaco em vez de underscore). Mais barato cadastrar o alias
    # aqui uma vez do que pedir pra editar os 7 arquivos pra bater com um
    # nome unico -- e cobre qualquer outro modelo futuro que repita a
    # mesma variacao de nome.
    "DESCRIÇÃO DO IMÓVEL": "{{imovel.descricao}}",
    "DESCRIÇÃO IMÓVEL": "{{imovel.descricao}}",
    "QUALIFICAR IMÓVEL": "{{imovel.descricao}}",
    "NÚMERO MATRÍCULA": "{{imovel.matricula}}",
    "NÚMERO CIRCUNSCRIÇÃO": "{{imovel.circunscricao}}",
    "CIDADE ESTADO CIRCUNSCRIÇÃO": "{{imovel.circunscricao}} Circunscrição da Comarca de {{imovel.comarca}}",
    "TITULO AQUISITIVO": "{{imovel.titulo_aquisitivo}}",
    "PREÇO VENDA": "{{valor}}",
    "VALOR VENDA": "{{valor}}",
    "VALOR DOAÇÃO": "{{valor}}",
    "VALOR_DOAÇÃO": "{{valor}}",
    "QUALIFICAR OUTORGANTE(S)": "{{#outorgantes}}" + "{{texto_qualificacao}}" + "{{/outorgantes}}",
    "QUALIFICAR OUTORGANTE DOADOR": "{{#outorgantes}}" + "{{texto_qualificacao}}" + "{{/outorgantes}}",
    "QUALIFICAR OUTORGANTE DEVEDOR": "{{#outorgantes}}" + "{{texto_qualificacao}}" + "{{/outorgantes}}",
    "QUALIFICAR OUTORGADO(S)": "{{#outorgados}}" + "{{texto_qualificacao}}" + "{{/outorgados}}",
    "QUALIFICAR OUTORGADO DONATÁRIO": "{{#outorgados}}" + "{{texto_qualificacao}}" + "{{/outorgados}}",
    "QUALIFICAR OUTORGADO CREDOR": "{{#outorgados}}" + "{{texto_qualificacao}}" + "{{/outorgados}}",
}


def normalizar_nome_variavel(bruto: str) -> str:
    """'<NUMERO_MATRICULA>' -> 'NUMERO_MATRICULA'; '  Nome conjuge   outorgante '
    -> 'NOME CONJUGE OUTORGANTE' -- pra bater com a chave do registro
    independente de espaco extra, <> nas pontas, ou maiuscula/minuscula."""
    limpo = bruto.strip().strip("<>").strip()
    limpo = re.sub(r"\s+", " ", limpo)
    return limpo.upper()


_PADRAO_CONCORDANCIA = re.compile(r"^(\S+):(\d+)$")


def _calcular_dispensas_certidoes(contexto: dict) -> str:
    """Monta o texto de «DISPENSAS_CERTIDOES_COMPRADOR» -- olha TODAS as
    pessoas (outorgantes e outorgados) e lista quais certidoes pessoais
    (dos 7 tipos fixos) nao foram apresentadas por cada uma. Se ninguem
    dispensou nada, devolve string vazia (a tag some sem deixar buraco).

    IMPORTANTE: a redacao abaixo e' um PLACEHOLDER -- o usuario disse que
    vai mandar o texto definitivo depois. Ate' la', o texto sai bem
    marcado como pendente, pra nunca ser confundido com redacao final
    aprovada numa escritura de verdade."""
    pendencias = []
    for grupo_nome, chave_contexto in [("outorgante", "outorgantes"), ("outorgado", "outorgados")]:
        pessoas = contexto.get(chave_contexto) or []
        for pessoa in pessoas:
            certidoes = pessoa.get("certidoes") or {}
            nome_pessoa = pessoa.get("nome") or pessoa.get("razao_social") or grupo_nome
            faltando = [
                nome_legivel for tipo_id, nome_legivel in TIPOS_CERTIDAO
                if not certidoes.get(tipo_id)
            ]
            if faltando:
                pendencias.append(f"{nome_pessoa}: {', '.join(faltando)}")

    if not pendencias:
        return ""

    lista = "; ".join(pendencias)
    return (
        f"[REDAÇÃO PENDENTE — texto definitivo a ser fornecido pelo tabelionato] "
        f"A parte outorgada/compradora declara ter sido informada da não apresentação das seguintes "
        f"certidões, e dispensa expressamente sua exigência, assumindo toda e qualquer "
        f"responsabilidade por eventual prejuízo decorrente, isentando este Tabelionato de "
        f"qualquer responsabilidade a respeito: {lista}."
    )


_MAPEAMENTO_CATEGORIAS_DISPENSA = [
    # (nome da categoria como aparece na frase, lista de tipo_id que fazem parte dela)
    ("feitos ajuizados Cíveis e Execuções fiscais", ["feitos_1_distribuidor", "feitos_2_distribuidor"]),
    ("Justiça Federal", ["feitos_trf"]),
    ("Justiça do Trabalho", ["feitos_trt"]),  # so' TRT -- debitos_trabalhistas NAO entra aqui
    ("Tributos Federais", ["tributos_federais"]),
    ("Tributos Estaduais", ["tributos_estaduais"]),
]


def _calcular_categorias_certidoes_faltantes(contexto: dict) -> str:
    """Monta a lista de categorias de certidao que estao faltando -- do
    OUTORGANTE principal E do conjuge dele quando o conjuge tambem
    outorga (co-vendedor) -- na redacao natural em portugues (com
    virgula e 'e' antes da ultima). Usada dentro da nova alinea de
    declaracao de dispensa no item 12 (ver texto fornecido pelo usuario).

    Uma categoria conta como "faltante" se faltou pra QUALQUER um dos
    outorgantes (titular ou conjuge) -- ex: se o titular apresentou a
    certidao trabalhista mas o conjuge nao, a categoria correspondente
    ainda entra na lista (falta apresentar POR COMPLETO aquele grupo).

    Retorna string vazia se nada estiver faltando -- nesse caso o
    paragrafo INTEIRO que contem essa tag e' removido do documento (ver
    _processar_paragrafo, que reconhece esse caso especial)."""
    # BUG HISTORICO CORRIGIDO: contexto NUNCA tem uma chave "outorgante"
    # (singular) -- desde que o sistema passou a suportar multiplos
    # outorgantes, o main.py so' preenche "outorgantes" (plural, lista).
    # A versao anterior desta funcao fazia contexto.get("outorgante"),
    # que sempre voltava {} -- ou seja, o conjuge outorgante NUNCA era
    # encontrado, pra NENHUM caso, desde essa mudanca. Corrigido pra
    # varrer a lista de verdade.
    outorgantes_lista = contexto.get("outorgantes") or (
        [contexto["outorgante"]] if contexto.get("outorgante") else []
    )
    pessoas_outorgantes = list(outorgantes_lista)
    for outorgante in outorgantes_lista:
        conjuge_info = outorgante.get("conjuge_participante")
        if conjuge_info and conjuge_info.get("participacao") == "outorga_tambem" and conjuge_info.get("dados"):
            pessoas_outorgantes.append(conjuge_info["dados"])

    categorias_faltantes = []
    for nome_categoria, tipos_da_categoria in _MAPEAMENTO_CATEGORIAS_DISPENSA:
        falta_pra_alguem = any(
            all(not (pessoa.get("certidoes") or {}).get(tipo_id) for tipo_id in tipos_da_categoria)
            for pessoa in pessoas_outorgantes
        )
        if falta_pra_alguem:
            categorias_faltantes.append(nome_categoria)

    imovel = contexto.get("imovel") or {}
    certidao_municipal = (imovel.get("certidoes_extras") or {}).get("tributos_municipais")
    if not certidao_municipal:
        categorias_faltantes.append("Tributos Municipais relativa ao imóvel")

    if not categorias_faltantes:
        return ""
    if len(categorias_faltantes) == 1:
        return categorias_faltantes[0]
    return ", ".join(categorias_faltantes[:-1]) + " e " + categorias_faltantes[-1]


_CAMPOS_PREENCHIDOS_SO_NA_LAVRATURA = {"ORDEM DE LAVRATURA", "DATA DE LAVRATURA"}


def _resolver_uma_tag(conteudo_tag: str, contexto: dict, concordancia_por_grupo: dict):
    """Resolve o conteudo de UMA tag «conteudo_tag» (sem os «» -- so' o
    que tem dentro). Retorna (valor_resolvido, aviso_ou_None)."""
    m = _PADRAO_CONCORDANCIA.match(conteudo_tag.strip())
    if m:
        palavra, grupo_str = m.group(1), int(m.group(2))
        conc = concordancia_por_grupo.get(grupo_str, {"numero": "sing", "genero": "m"})
        numero = conc.get("numero", "sing")
        if palavra in PALAVRAS_PESSOA:
            genero = conc.get("genero", "m")
            chave = ("m" if genero == "m" else "f") + ("s" if numero == "sing" else "p")
            return PALAVRAS_PESSOA[palavra][chave], None
        if palavra in PALAVRAS_NUMERO_FIXO:
            chave = "s" if numero == "sing" else "p"
            return PALAVRAS_NUMERO_FIXO[palavra][chave], None
        return (
            f"«{conteudo_tag}»",
            f"Palavra de concordância desconhecida: «{conteudo_tag}» -- não cadastrada, mantida como está.",
        )

    chave_normalizada = normalizar_nome_variavel(conteudo_tag)

    # Caso especial -- nao e' um molde {{}} estatico, precisa OLHAR o
    # dado real de cada pessoa pra saber quais certidoes faltaram.
    if chave_normalizada == "DISPENSAS_CERTIDOES_COMPRADOR":
        return _calcular_dispensas_certidoes(contexto), None

    if chave_normalizada == "CATEGORIAS_CERTIDOES_FALTANTES":
        return _calcular_categorias_certidoes_faltantes(contexto), None

    if chave_normalizada in REGISTRO_VARIAVEIS:
        molde = REGISTRO_VARIAVEIS[chave_normalizada]
        valor = _substituir_variaveis(molde, contexto)
        # Ordem/data de lavratura sao preenchidas fisicamente no MOMENTO
        # da lavratura, nao antes -- igual a "Lista CNIB" (que nem tem
        # mapeamento em REGISTRO_VARIAVEIS, por isso ja' fica intocada
        # sozinha). Aqui SIM tem mapeamento (porque as vezes o tabeliao
        # ja' sabe o numero/data com antecedencia e quer preencher), mas
        # quando NAO informado, a tag fica como estava no lugar de virar
        # um "[FALTA: ...]" -- nao e' um dado faltando por erro, e' um
        # dado que só existe dali a pouco.
        if chave_normalizada in _CAMPOS_PREENCHIDOS_SO_NA_LAVRATURA and valor.startswith("[FALTA:"):
            return f"«{conteudo_tag}»", None
        return valor, None

    return (
        f"«{conteudo_tag}»",
        f"Variável desconhecida: «{conteudo_tag}» -- não cadastrada em REGISTRO_VARIAVEIS, mantida como está no documento.",
    )


_PADRAO_TAG_GERAL = re.compile(r"«([^«»]+)»")


def _preparar_contexto(contexto: dict) -> dict:
    """Enriquece outorgantes/outorgados com os campos de concordancia
    individual (portador_a etc.), igual o motor_minuta.py ja' faz --
    precisa disso pra {{#outorgantes}}...{{/outorgantes}} funcionar
    dentro das variaveis de qualificacao.

    Tambem garante que tanto a chave SINGULAR ('outorgante') quanto a
    LISTA ('outorgantes') existam, derivando uma da outra se so' uma
    delas vier preenchida -- o tratamento de certidao («CERTIDAO:tipo»)
    depende da chave singular pra saber de quem e' a certidao, e nem
    todo chamador necessariamente popula as duas."""
    contexto = dict(contexto)
    if contexto.get("outorgantes"):
        contexto["outorgantes"] = [enriquecer_pessoa_com_concordancia(p) for p in contexto["outorgantes"]]
        contexto.setdefault("outorgante", contexto["outorgantes"][0])
    elif contexto.get("outorgante"):
        contexto["outorgante"] = enriquecer_pessoa_com_concordancia(contexto["outorgante"])
        contexto.setdefault("outorgantes", [contexto["outorgante"]])

    if contexto.get("outorgados"):
        contexto["outorgados"] = [enriquecer_pessoa_com_concordancia(p) for p in contexto["outorgados"]]
        contexto.setdefault("outorgado", contexto["outorgados"][0])
    elif contexto.get("outorgado"):
        contexto["outorgado"] = enriquecer_pessoa_com_concordancia(contexto["outorgado"])
        contexto.setdefault("outorgados", [contexto["outorgado"]])

    return contexto


def _calcular_concordancia_por_grupo(contexto: dict) -> dict:
    outorgantes = contexto.get("outorgantes") or ([contexto["outorgante"]] if contexto.get("outorgante") else [])
    outorgados = contexto.get("outorgados") or ([contexto["outorgado"]] if contexto.get("outorgado") else [])
    qtd_imoveis = len(contexto.get("imoveis") or [1])
    return {
        1: calcular_concordancia_grupo(outorgantes),
        2: calcular_concordancia_grupo(outorgados),
        4: calcular_concordancia_quantidade(qtd_imoveis),
    }


def _copiar_formato(run_origem, run_novo):
    run_novo.bold = run_origem.bold
    run_novo.italic = run_origem.italic
    run_novo.underline = run_origem.underline
    try:
        if run_origem.font.size:
            run_novo.font.size = run_origem.font.size
        if run_origem.font.name:
            run_novo.font.name = run_origem.font.name
        if run_origem.font.color and run_origem.font.color.rgb:
            run_novo.font.color.rgb = run_origem.font.color.rgb
    except Exception:
        pass  # formatacao extra e' um "bonus" -- nunca pode quebrar o preenchimento


def _adicionar_texto_com_negrito_embutido(paragrafo, texto: str, run_origem=None):
    """Adiciona 'texto' ao paragrafo interpretando **assim** como negrito
    de verdade (nao so' asterisco literal) -- convencao usada dentro de
    texto_qualificacao (ver _nome_negrito_maiusculo em concordancia.py,
    que ja' devolve o nome da parte como '**NOME EM MAIUSCULO**').

    Sem isso, o valor resolvido de uma tag como «<QUALIFICAR_OUTORGANTE>»
    apareceria no documento final com os asteriscos literais em volta do
    nome, em vez do nome em negrito -- porque o resto do resolvedor so'
    copia a formatacao do texto ORIGINAL do template ao redor da tag, e
    esse texto original nao tem nenhum '**' pra interpretar por conta
    propria.

    Cada pedaco em negrito vira um run PROPRIO (senao um paragrafo com
    varios trechos em negrito intercalados > 1 vez ficaria com o negrito
    "vazando" pro texto normal seguinte)."""
    if "**" not in texto:
        novo_run = paragrafo.add_run(texto)
        if run_origem is not None:
            _copiar_formato(run_origem, novo_run)
        return
    partes = texto.split("**")
    for indice, parte in enumerate(partes):
        if parte == "":
            continue
        novo_run = paragrafo.add_run(parte)
        if run_origem is not None:
            _copiar_formato(run_origem, novo_run)
        if indice % 2 == 1:
            novo_run.bold = True


_PADRAO_CERTIDAO_MARCADOR = re.compile(r"«CERTIDAO:([^«»:]+)(?::([^«»]+))?»")


def _resolver_tags_em_texto(texto: str, contexto: dict, concordancia_por_grupo: dict) -> tuple[str, list[str]]:
    """Versao 'texto puro' da resolucao de tags (concordancia + variaveis)
    -- sem lidar com runs/formatacao, usada em pedacos de texto que ja'
    saíram do fluxo normal de paragrafo (ex: o prefixo e o restante de um
    paragrafo tratado pelo mecanismo de «CERTIDAO:...», que tem suas
    proprias tags de concordancia/variavel MISTURADAS com as tags
    especificas de certidao)."""
    avisos = []

    def resolver(m):
        valor, aviso = _resolver_uma_tag(m.group(1), contexto, concordancia_por_grupo)
        if aviso:
            avisos.append(aviso)
        return valor

    texto_resolvido = _PADRAO_TAG_GERAL.sub(resolver, texto)
    return texto_resolvido, avisos


def _processar_paragrafo_certidao(paragrafo, contexto: dict, concordancia_por_grupo: dict) -> tuple[bool, list[str], list[str]]:
    """Se o paragrafo tiver uma marca «CERTIDAO:tipo» (ou
    «CERTIDAO:lado:tipo»), cuida do paragrafo INTEIRO: troca o texto
    depois da marca pela frase de dispensa (se a certidao nao foi
    enviada) ou preenche «<CERT_NUMERO>»/«<CERT_DATA_EMISSAO>»/
    «<CERT_DATA_VALIDADE>»/«<CERT_SITUACAO>» com o dado real (se foi).
    O texto ANTES da marca (tipicamente so' a letra, ex: 'b)') fica
    intocado, entao nunca precisa renumerar nada.

    Retorna (era_paragrafo_de_certidao, avisos, alertas_criticos).
    Se nao encontrar a marca, retorna (False, [], []) e quem chamou
    segue com o processamento generico normal desse paragrafo."""
    runs_originais = list(paragrafo.runs)
    texto_completo = "".join(r.text for r in runs_originais)

    m = _PADRAO_CERTIDAO_MARCADOR.search(texto_completo)
    if not m:
        return False, [], []

    lado = "outorgante"
    tipo_id = m.group(1).strip()
    if m.group(2):  # forma «CERTIDAO:lado:tipo»
        lado, tipo_id = m.group(1).strip(), m.group(2).strip()

    prefixo = texto_completo[:m.start()]
    resto = texto_completo[m.end():]

    avisos = []
    alertas_criticos = []

    def _remover_paragrafo():
        for run in runs_originais:
            run._element.getparent().remove(run._element)
        elemento = paragrafo._element
        pai = elemento.getparent()
        if pai is not None:
            pai.remove(elemento)

    if lado == "imovel":
        # Certidao do IMOVEL (ex: tributos municipais) -- fica em
        # imovel.certidoes_extras, nao em pessoa.certidoes, ja que nao
        # pertence a nenhuma pessoa especifica. Diferente das certidoes
        # PESSOAIS abaixo, essa NUNCA e' removida do documento quando
        # falta -- e' uma clausula substantiva (item 8, situacao fiscal),
        # nao um item de LISTA de "documentos apresentados" -- por isso
        # continua mostrando pendencia inline, em vez de sumir.
        imovel = contexto.get("imovel") or {}
        certidao = (imovel.get("certidoes_extras") or {}).get(tipo_id)
        lado_rotulo = "imóvel"
    elif lado == "ambos":
        # NOVO (pedido explicito do usuario): em vez de uma alinea pro
        # titular (b, e, f, g, h) e outra separada pro conjuge outorgante
        # (i, l, m, n, o -- ver branch "outorgante_conjuge" abaixo, que
        # continua existindo pra quem preferir alineas separadas), esse
        # modo junta os dois numeros NUMA ALINEA SO', no formato "sob nºs
        # X e Y". So' usar esse marcador em templates cuja redacao ja'
        # esteja no plural ("Certidões... sob nºs «<CERT_NUMERO>»").
        outorgantes_lista = contexto.get("outorgantes") or (
            [contexto["outorgante"]] if contexto.get("outorgante") else []
        )
        outorgante_principal = next(
            (o for o in outorgantes_lista if (o.get("conjuge_participante") or {}).get("participacao") == "outorga_tambem"),
            None,
        )
        pessoa_titular = outorgante_principal if outorgante_principal is not None else (outorgantes_lista[0] if outorgantes_lista else {})
        pessoa_conjuge = (outorgante_principal or {}).get("conjuge_participante", {}).get("dados") if outorgante_principal else None

        certidao_titular = (pessoa_titular.get("certidoes") or {}).get(tipo_id)
        certidao_conjuge = (pessoa_conjuge.get("certidoes") or {}).get(tipo_id) if pessoa_conjuge else None
        pares = [(p, c) for p, c in [(pessoa_titular, certidao_titular), (pessoa_conjuge, certidao_conjuge)] if c]

        if not pares:
            # nem o titular nem o conjuge tem essa certidao -- a alinea
            # some igual ao comportamento de certidao pessoal unica (vai
            # entrar na declaracao consolidada do item 12, nao aqui).
            _remover_paragrafo()
            return True, avisos, alertas_criticos

        numeros = [c.get("numero") or "[FALTA: numero]" for _, c in pares]
        datas_emissao = [c.get("data_emissao") or "[FALTA: data_emissao]" for _, c in pares]
        datas_validade = [c.get("data_validade") for _, c in pares]
        situacoes_brutas = [(c.get("situacao") or "").strip().lower() for _, c in pares]

        if any(s == "positiva" for s in situacoes_brutas):
            nome_legivel = _NOMES_LEGIVEIS_CERTIDAO.get(tipo_id, tipo_id)
            alertas_criticos.append(
                f"⚠️ {nome_legivel} veio POSITIVA pra pelo menos um dos outorgantes — confira antes de prosseguir."
            )
        # Normalmente ambas vem com a mesma situacao (negativa/negativa) --
        # se por acaso vierem diferentes, usa a mais severa (positiva
        # prevalece sobre negativa) pra nao esconder um problema.
        situacao_escolhida = "positiva" if "positiva" in situacoes_brutas else situacoes_brutas[0]
        situacao_legivel = _SITUACAO_LEGIVEL.get(situacao_escolhida, pares[0][1].get("situacao") or "[FALTA: situacao]")

        def _juntar(valores):
            unicos = list(dict.fromkeys(valores))  # remove duplicata mantendo ordem, sem precisar ordenar
            return " e ".join(unicos)

        substituicoes = {
            "CERT_NUMERO": _juntar(numeros),
            "CERT_DATA_EMISSAO": _juntar(datas_emissao),
            "CERT_DATA_VALIDADE": _juntar([d or "[FALTA: data_validade]" for d in datas_validade]),
            "CERT_SITUACAO": situacao_legivel,
        }
        resto_preenchido = resto
        for nome_tag, valor in substituicoes.items():
            resto_preenchido = re.sub(rf"«<?{nome_tag}>?»", valor, resto_preenchido)
        novo_texto = prefixo + resto_preenchido

        novo_texto, avisos_gerais = _resolver_tags_em_texto(novo_texto, contexto, concordancia_por_grupo)
        avisos.extend(avisos_gerais)
        for run in runs_originais:
            run._element.getparent().remove(run._element)
        _adicionar_texto_com_negrito_embutido(paragrafo, novo_texto, runs_originais[0] if runs_originais else None)
        return True, avisos, alertas_criticos

    elif lado == "outorgante_conjuge":
        # Certidao do CONJUGE que tambem outorga (co-vendedor) -- so'
        # faz sentido mostrar essa alinea se o outorgante principal TEM
        # um conjuge participando como "outorga_tambem". Se nao tem
        # conjuge nenhum, ou o conjuge so' anui/so' qualifica, essa
        # alinea inteira NUNCA deveria aparecer no documento -- remove o
        # paragrafo, nao deixa buraco nem "pendencia" de algo que nem
        # existe.
        # Mesmo bug historico do contexto.get("outorgante") corrigido aqui
        # -- ver comentario extenso em _calcular_categorias_certidoes_faltantes.
        # Varre a lista de outorgantes de verdade procurando qual deles
        # (normalmente so' existe um nesse cenario) tem um conjuge que
        # tambem outorga -- e' esse o "outorgante principal" pra fins
        # desta alinea de certidao do conjuge.
        outorgantes_lista = contexto.get("outorgantes") or (
            [contexto["outorgante"]] if contexto.get("outorgante") else []
        )
        outorgante_principal = next(
            (o for o in outorgantes_lista if (o.get("conjuge_participante") or {}).get("participacao") == "outorga_tambem"),
            {},
        )
        conjuge_info = outorgante_principal.get("conjuge_participante")
        if not conjuge_info or conjuge_info.get("participacao") != "outorga_tambem":
            _remover_paragrafo()
            return True, avisos, alertas_criticos
        pessoa = conjuge_info.get("dados") or {}
        lado_rotulo = "cônjuge outorgante"
        certidao = (pessoa.get("certidoes") or {}).get(tipo_id)
    else:
        pessoa = contexto.get(lado)
        if not pessoa:
            avisos.append(f"«CERTIDAO:{tipo_id}»: não há '{lado}' no contexto -- paragrafo mantido sem alteração.")
            texto_resolvido, avisos_gerais = _resolver_tags_em_texto(prefixo + resto, contexto, concordancia_por_grupo)
            avisos.extend(avisos_gerais)
            for run in runs_originais:
                run._element.getparent().remove(run._element)
            novo_run = paragrafo.add_run(texto_resolvido)
            if runs_originais:
                _copiar_formato(runs_originais[0], novo_run)
            return True, avisos, alertas_criticos
        lado_rotulo = lado
        certidao = (pessoa.get("certidoes") or {}).get(tipo_id)

    if not certidao:
        if lado == "imovel":
            # Item 8 (situacao fiscal) e' substantivo -- continua
            # mostrando "[PENDENTE: ...]" inline quando falta, nunca some.
            nome_legivel = _NOMES_LEGIVEIS_CERTIDAO.get(tipo_id, tipo_id)
            alertas_criticos.append(
                f"⚠️ {nome_legivel} do(a) {lado_rotulo} não foi apresentada nem dispensada — revise antes de assinar."
            )
            novo_texto = prefixo + " " + _texto_certidao_obrigatoria_pendente(tipo_id)
        else:
            # Certidao PESSOAL (outorgante, outorgado ou conjuge) que nao
            # foi enviada: a alinea inteira DESAPARECE do item 14 -- o
            # texto de dispensa/pendencia nao fica mais espalhado
            # certidao por certidao aqui. Em vez disso, uma UNICA
            # declaracao consolidada entra no item 12 (ver
            # «CATEGORIAS_CERTIDOES_FALTANTES» / _calcular_categorias_
            # certidoes_faltantes), citando so' as categorias que
            # realmente faltaram, juntas numa frase so'.
            _remover_paragrafo()
            return True, avisos, alertas_criticos
    else:
        situacao_bruta = (certidao.get("situacao") or "").strip().lower()
        situacao_legivel = _SITUACAO_LEGIVEL.get(situacao_bruta, certidao.get("situacao") or "[FALTA: situacao]")
        if situacao_bruta == "positiva":
            nome_legivel = _NOMES_LEGIVEIS_CERTIDAO.get(tipo_id, tipo_id)
            alertas_criticos.append(
                f"⚠️ {nome_legivel} do(a) {lado_rotulo} veio POSITIVA — confira antes de prosseguir."
            )
        substituicoes = {
            "CERT_NUMERO": certidao.get("numero") or "[FALTA: numero]",
            "CERT_DATA_EMISSAO": certidao.get("data_emissao") or "[FALTA: data_emissao]",
            "CERT_DATA_VALIDADE": certidao.get("data_validade") or "[FALTA: data_validade]",
            "CERT_SITUACAO": situacao_legivel,
        }
        resto_preenchido = resto
        for nome_tag, valor in substituicoes.items():
            resto_preenchido = re.sub(rf"«<?{nome_tag}>?»", valor, resto_preenchido)

        if lado == "outorgante_conjuge":
            # Deixa explicito de quem e' essa certidao -- sem isso, a
            # alinea do conjuge ficaria com o MESMO texto da alinea do
            # titular, sem nada indicando que sao pessoas diferentes.
            nome_conjuge = pessoa.get("nome") or "cônjuge outorgante"
            resto_preenchido = f" (do(a) cônjuge outorgante, {nome_conjuge}){resto_preenchido}"

        novo_texto = prefixo + resto_preenchido

    # O prefixo (antes da marca «CERTIDAO:...») e o restante do paragrafo
    # podem ter OUTRAS tags de concordancia/variavel misturadas (ex:
    # «O:4» «imóvel:4» antes da marca, «<INDICACAO_FISCAL>» depois) --
    # isso e' resolvido AQUI, depois das substituicoes especificas de
    # certidao, pra pegar tudo que sobrar.
    novo_texto, avisos_gerais = _resolver_tags_em_texto(novo_texto, contexto, concordancia_por_grupo)
    avisos.extend(avisos_gerais)

    for run in runs_originais:
        run._element.getparent().remove(run._element)
    _adicionar_texto_com_negrito_embutido(paragrafo, novo_texto, runs_originais[0] if runs_originais else None)

    return True, avisos, alertas_criticos


def _processar_paragrafo(paragrafo, contexto: dict, concordancia_por_grupo: dict) -> list[str]:
    """Substitui as tags «» de UM paragrafo, preservando a formatacao
    (negrito etc.) de cada trecho -- reconstroi os runs do paragrafo do
    zero, usando o formato do run ORIGINAL de onde cada pedaco de texto
    veio. Retorna a lista de avisos encontrados nesse paragrafo."""
    runs_originais = list(paragrafo.runs)
    texto_completo = "".join(r.text for r in runs_originais)
    if "«" not in texto_completo:
        return []

    # Caso especial: se o paragrafo tiver a tag de categorias de
    # certidao faltante (nova clausula de dispensa consolidada no item
    # 12) e nao faltar NADA, o paragrafo INTEIRO some -- nao faz sentido
    # nenhuma frase de "dispensa a apresentacao de ______" sobrando sem
    # nada pra dispensar.
    for m in _PADRAO_TAG_GERAL.finditer(texto_completo):
        if normalizar_nome_variavel(m.group(1)) == "CATEGORIAS_CERTIDOES_FALTANTES":
            if not _calcular_categorias_certidoes_faltantes(contexto):
                elemento = paragrafo._element
                pai = elemento.getparent()
                if pai is not None:
                    pai.remove(elemento)
                return []
            break

    mapa_runs = []
    for i, run in enumerate(runs_originais):
        mapa_runs.extend([i] * len(run.text))

    def run_na_posicao(pos):
        if not mapa_runs:
            return 0
        return mapa_runs[min(pos, len(mapa_runs) - 1)]

    segmentos = []  # (texto, indice_do_run_de_origem)
    avisos = []
    pos = 0
    for m in _PADRAO_TAG_GERAL.finditer(texto_completo):
        inicio, fim = m.span()
        if inicio > pos:
            segmentos.append((texto_completo[pos:inicio], run_na_posicao(pos)))
        valor, aviso = _resolver_uma_tag(m.group(1), contexto, concordancia_por_grupo)
        if aviso:
            avisos.append(aviso)
        segmentos.append((valor, run_na_posicao(inicio)))
        pos = fim
    if pos < len(texto_completo):
        segmentos.append((texto_completo[pos:], run_na_posicao(pos)))

    for run in runs_originais:
        run._element.getparent().remove(run._element)

    for texto_seg, indice_origem in segmentos:
        if texto_seg == "":
            continue
        _adicionar_texto_com_negrito_embutido(
            paragrafo, texto_seg, runs_originais[indice_origem] if runs_originais else None
        )

    return avisos


def processar_docx(caminho_entrada: str, caminho_saida: str, contexto: dict, condicoes: dict | None = None) -> dict:
    """Abre o .docx de ENTRADA (o modelo com as tags «»), resolve tudo
    (concordancia + variaveis + certidoes), preservando formatacao, e
    salva no caminho de SAIDA.

    Retorna um dict {"avisos": [...], "alertas_criticos": [...]}:
      - 'avisos': coisas informativas (variavel desconhecida, campo sem
        valor) -- nao impedem o uso do documento, so' merecem atencao.
      - 'alertas_criticos': coisas que precisam de decisao humana ANTES
        de prosseguir (hoje, so' certidao com situacao 'positiva' pura)
        -- o texto e' preenchido normalmente mesmo assim, o alerta e' so'
        pra chamar atencao, nao trava a geracao."""
    from docx import Document

    contexto = _preparar_contexto(contexto)
    concordancia_por_grupo = _calcular_concordancia_por_grupo(contexto)

    doc = Document(caminho_entrada)
    avisos = []
    alertas_criticos = []

    def processar_paragrafos(lista_paragrafos):
        for p in lista_paragrafos:
            era_certidao, avisos_cert, alertas_cert = _processar_paragrafo_certidao(p, contexto, concordancia_por_grupo)
            if era_certidao:
                avisos.extend(avisos_cert)
                alertas_criticos.extend(alertas_cert)
                continue
            avisos.extend(_processar_paragrafo(p, contexto, concordancia_por_grupo))

    processar_paragrafos(doc.paragraphs)
    for tabela in doc.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                processar_paragrafos(celula.paragraphs)

    # Texto sempre justificado -- convencao pedida pra toda escritura.
    # Pula paragrafos com estilo "Heading*" (titulo da escritura) pra nao
    # forcar justificado num titulo que normalmente e' centralizado pelo
    # proprio estilo do Word.
    for p in doc.paragraphs:
        if not (p.style and p.style.name or "").startswith("Heading"):
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for tabela in doc.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                for p in celula.paragraphs:
                    if not (p.style and p.style.name or "").startswith("Heading"):
                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # Tipografia sempre Arial 12 -- convencao pedida pra TODA a escritura,
    # independente da fonte que o .docx modelo tiver originalmente. Forca
    # em CADA run do documento (nao so' nos que a resolucao de tags
    # tocou), inclusive titulo -- Arial 12 vale pra tudo, negrito
    # continua negrito, so' a fonte/tamanho que padroniza.
    for p in doc.paragraphs:
        for run in p.runs:
            run.font.name = "Arial"
            run.font.size = Pt(12)
    for tabela in doc.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                for p in celula.paragraphs:
                    for run in p.runs:
                        run.font.name = "Arial"
                        run.font.size = Pt(12)

    doc.save(caminho_saida)
    return {"avisos": avisos, "alertas_criticos": alertas_criticos}
