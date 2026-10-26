"""
Motor de composicao de minuta por ITEM FRAGMENTADO -- cada MODELO (tipo de
ato) tem seus proprios itens, totalmente independentes uns dos outros
(sem nada compartilhado por tras) -- monta a minuta aplicando as
variantes condicionais de acordo com o contexto do caso, e substitui as
variaveis {{ }} pelos dados reais.

Isso substitui o modelo antigo de "um .docx fixo por tipo de ato" por
"itens fragmentados por item + regras de variante", mas cada tipo de ato
e' um bloco proprio em dados/itens_minuta.json -- editar o COAF de Compra
e Venda NAO afeta o COAF de Doacao, por exemplo, mesmo que o texto comece
identico. Essa independencia foi decisao explicita: mais texto duplicado
pra cadastrar, mas zero risco de uma mudanca num modelo vazar pra outro
sem querer.

USO:
    from motor_minuta import montar_minuta
    texto, avisos = montar_minuta("compra_e_venda_a_vista", contexto, condicoes)

Onde 'condicoes' e' um dict de flags booleanas/valores que ativam as
variantes (ex: {"onus_existe": True, "outorgado_pj": False, ...}).
"""
import json
import os
import re
import string

from concordancia import (
    resolver_concordancia, calcular_concordancia_grupo,
    calcular_concordancia_quantidade, enriquecer_pessoa_com_concordancia,
)

CAMINHO_DADOS = os.path.join(os.path.dirname(__file__), "..", "dados", "itens_minuta.json")

# Variaveis cujo valor vazio ("") e' um resultado LEGITIMO -- clausulas
# condicionais que so' aparecem quando alguma coisa especial acontece
# (ha' onus, a venda e' de fracao ideal, o outorgante tem conjuge
# participante) e ficam propositalmente em branco no caso comum. Sem essa
# lista, "" e None eram tratados igual (as duas viravam "[FALTA: ...]"),
# entao toda escritura sem onus/sem fracao parcial/sem conjuge SEMPRE
# mostrava um "[FALTA: onus_citacao]" (etc.) sobrando no meio do texto --
# um falso alarme, ja' que ali "vazio" era exatamente o esperado.
_CAMPOS_QUE_PODEM_FICAR_VAZIOS = {
    "onus_citacao", "parte_ideal_texto", "conjuge_outorgante_texto",
}


def _carregar_dados() -> dict:
    with open(CAMINHO_DADOS, "r", encoding="utf-8") as f:
        return json.load(f)


def _substituir_variaveis(texto: str, contexto: dict) -> str:
    """Substitui {{caminho.pontuado}} pelo valor correspondente em
    contexto (dict aninhado). Placeholder sem valor encontrado vira uma
    marcacao visivel [FALTA: caminho], em vez de sumir silenciosamente --
    isso ajuda a notar campo esquecido em vez de gerar minuta com buraco
    invisivel no meio do texto.

    Tambem suporta um bloco de REPETICAO simples, pra listar N itens de
    uma lista (ex: varios outorgantes) sem precisar de um item de texto
    por pessoa:

        {{#outorgantes}}{{nome}}, {{nacionalidade}}{{/outorgantes}}

    Isso repete o texto entre as tags uma vez pra cada elemento da lista
    'outorgantes' do contexto, resolvendo {{nome}}/{{nacionalidade}} DENTRO
    do contexto de cada elemento -- e junta o resultado com '; ' (separador
    fixo, simples de prever). Isso NAO substitui o uso antigo
    {{outorgante.nome}} (singular) -- os dois convivem; o backend continua
    populando 'outorgante'/'outorgado' com o primeiro da lista por
    compatibilidade com item ja cadastrado que nao usa o bloco de
    repeticao."""

    def resolver_repeticao(match):
        chave_lista = match.group(1).strip()
        template_interno = match.group(2)
        lista = contexto.get(chave_lista)
        if not isinstance(lista, list) or not lista:
            return f"[FALTA: {chave_lista}]"
        pedacos = []
        for elemento in lista:
            contexto_elemento = elemento if isinstance(elemento, dict) else {"valor": elemento}
            pedacos.append(_substituir_variaveis(template_interno, contexto_elemento))
        return "; ".join(pedacos)

    texto = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", resolver_repeticao, texto, flags=re.DOTALL)

    def resolver(match):
        caminho = match.group(1).strip()
        partes = caminho.split(".")
        valor = contexto
        for parte in partes:
            if isinstance(valor, dict) and parte in valor:
                valor = valor[parte]
            else:
                return f"[FALTA: {caminho}]"
        if valor is None or valor == "":
            if caminho in _CAMPOS_QUE_PODEM_FICAR_VAZIOS:
                return ""
            return f"[FALTA: {caminho}]"
        return str(valor)

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", resolver, texto)


def _aplicar_variantes(bloco: dict, contexto: dict, condicoes: dict, rotulo: str) -> tuple[str, list[str]]:
    """Aplica as variantes condicionais de UM bloco (um item simples, ou
    um sub-item dentro de um item) e substitui as variaveis {{ }}.
    'rotulo' e' so' pro texto dos avisos (identifica de onde veio, ex:
    'Item 14' ou 'Item 14 / certidao_trabalhista'). Retorna
    (texto_final, avisos) -- funcao pura, sem logica de dispensa (essa
    fica em montar_item, que decide SE um bloco entra ou nao antes de
    chamar isso)."""
    avisos = []
    if bloco.get("pendente"):
        avisos.append(f"'{rotulo}' ainda não tem texto definitivo cadastrado (placeholder).")

    texto = bloco.get("texto_padrao", "")
    substituiu = False

    for variante in bloco.get("variantes", []):
        vid = variante.get("id", "")
        if not vid or not condicoes.get(vid):
            continue

        acao = variante.get("acao", "")
        texto_variante = variante.get("texto", "")
        if acao == "substitui":
            if substituiu:
                avisos.append(f"'{rotulo}': mais de uma variante de substituição ativa ao mesmo tempo ({vid}).")
            texto = texto_variante
            substituiu = True
        elif acao == "adiciona_ao_final":
            texto = texto.rstrip(".") + texto_variante
        elif acao in ("adiciona_letra_extra",):
            # concatena como paragrafo/letra nova ao final do item
            texto = texto + "\n" + texto_variante
        elif acao == "adiciona_inline":
            # concatena na mesma frase, sem quebra de paragrafo (ex: item 11
            # emendando "; c) ..." direto na sequencia de b)
            texto = texto + texto_variante
        elif acao == "adiciona_ao_final_da_letra_a":
            # insere logo depois da letra "a)" -- caso especifico do item 11
            texto = re.sub(r"(a\)[^;]*)", lambda m: m.group(1) + texto_variante, texto, count=1)
        elif acao == "inclui_letra_b":
            texto = re.sub(r"(b\)[^;]*)", lambda m: m.group(1) + texto_variante, texto, count=1)
        elif acao == "inclui_letra_c":
            pass  # inclusao condicional simples, sem texto extra alem do padrao
        else:
            avisos.append(f"'{rotulo}': ação de variante desconhecida ou vazia ('{acao}') na variante '{vid}' -- ignorada.")

    texto_final = _substituir_variaveis(texto, contexto)

    faltando = re.findall(r"\[FALTA: ([\w.]+)\]", texto_final)
    for campo in faltando:
        avisos.append(f"'{rotulo}': campo '{campo}' não foi preenchido.")

    return texto_final, avisos


def montar_item(item_id: str, itens_do_modelo: dict, contexto: dict, condicoes: dict) -> tuple[str, list[str]]:
    """Monta o texto final de UM item (dentro dos itens do modelo/tipo de
    ato ja carregado), aplicando as variantes cuja condicao esteja ativa
    em 'condicoes'. Retorna (texto_final, avisos).

    Suporta dois formatos de item, pra manter 100% compatibilidade com
    o que ja existia:

    1. Item SIMPLES (formato antigo, continua igual): tem 'texto_padrao'
       e 'variantes' direto no proprio item -- uma unica unidade de
       texto, com variantes que trocam/emendam nesse texto.

    2. Item com SUB_ITENS (formato novo): tem uma lista 'sub_itens', cada
       um com seu proprio 'texto_padrao'/'variantes' independentes, e um
       campo opcional 'dispensavel_se' -- se a condicao nomeada ali
       estiver True em 'condicoes', aquele sub-item especifico SOME
       inteiro do resultado (nao aparece nem a letra), sem afetar os
       outros sub-itens do mesmo item. Isso e' o que permite, por
       exemplo, cada certidao (fiscal, trabalhista, distribuidor...) ser
       dispensada individualmente dentro do mesmo item 'Documentos e
       certidoes', em vez de ser tudo-ou-nada como a variante unica
       'certidoes_dispensadas' fazia antes.
    """
    if item_id not in itens_do_modelo:
        return f"[ITEM DESCONHECIDO: {item_id}]", [f"Item '{item_id}' não existe neste modelo."]

    item = itens_do_modelo[item_id]
    nome_item = item.get("nome", item_id)
    avisos = []

    if item.get("pendente"):
        avisos.append(f"Item '{nome_item}' ainda não tem texto definitivo cadastrado (placeholder).")

    if "sub_itens" in item:
        # Primeiro filtra quais sub-itens sobrevivem (nao dispensados),
        # DEPOIS numera as letras (a, b, c...) só entre os sobreviventes --
        # assim a sequencia nunca fica com buraco (ex: se o sub-item "b"
        # for dispensado, o que era "c" vira "b" automaticamente). Cada
        # sub-item usa o placeholder {{letra}} no proprio texto_padrao em
        # vez de escrever a letra fixa (ex: '{{letra}}) Débitos
        # Trabalhistas...' em vez de 'b) Débitos Trabalhistas...').
        sobreviventes = []
        for sub in item["sub_itens"]:
            dispensa_id = sub.get("dispensavel_se")
            if dispensa_id and condicoes.get(dispensa_id):
                continue  # dispensa esperada, nao e' erro -- sub-item some inteiro, nem letra usa
            sobreviventes.append(sub)

        partes_texto = []
        indice_letra = 0
        for sub in sobreviventes:
            sub_id = sub.get("id", "?")
            if sub.get("sem_letra"):
                # sub-item de cabecalho/introducao -- nao entra na
                # contagem de letras (a, b, c...), so' e' renderizado
                contexto_com_letra = contexto
            else:
                letra = string.ascii_lowercase[indice_letra] if indice_letra < 26 else f"({indice_letra + 1})"
                contexto_com_letra = {**contexto, "letra": letra}
                indice_letra += 1

            rotulo = f"Item '{nome_item}' / sub-item '{sub_id}'"
            texto_sub, avisos_sub = _aplicar_variantes(sub, contexto_com_letra, condicoes, rotulo)
            if texto_sub.strip():
                partes_texto.append(texto_sub)
            avisos.extend(avisos_sub)

        texto_final = "\n".join(partes_texto)
        return texto_final, avisos

    # formato antigo (item simples, sem sub_itens) -- comportamento identico ao de antes
    texto_final, avisos_item = _aplicar_variantes(item, contexto, condicoes, f"Item '{nome_item}'")
    avisos.extend(avisos_item)
    return texto_final, avisos


def montar_minuta(tipo_ato: str, contexto: dict, condicoes: dict) -> tuple[str, list[str]]:
    """Monta a minuta inteira pro tipo de ato pedido. Retorna
    (texto_completo, avisos_agregados)."""
    dados = _carregar_dados()

    if tipo_ato not in dados["modelos"]:
        disponiveis = list(dados["modelos"].keys())
        raise ValueError(f"Tipo de ato '{tipo_ato}' não tem modelo cadastrado. Disponíveis: {disponiveis}")

    modelo = dados["modelos"][tipo_ato]
    itens_do_modelo = modelo["itens"]
    ordem_itens = modelo["ordem"]

    # Enriquece cada pessoa (das listas outorgantes/outorgados) com os
    # campos de concordancia individual (portador_a, inscrito_a,
    # residente_domiciliado_a) ANTES de montar -- assim ficam disponiveis
    # dentro de {{#outorgantes}}...{{/outorgantes}} pra qualificacao.
    contexto = dict(contexto)  # nao mutar o dict que veio de fora
    if contexto.get("outorgantes"):
        contexto["outorgantes"] = [enriquecer_pessoa_com_concordancia(p) for p in contexto["outorgantes"]]
    if contexto.get("outorgados"):
        contexto["outorgados"] = [enriquecer_pessoa_com_concordancia(p) for p in contexto["outorgados"]]

    blocos = []
    avisos_totais = []

    for item_id in ordem_itens:
        texto_item, avisos_item = montar_item(item_id, itens_do_modelo, contexto, condicoes)
        blocos.append(texto_item)
        avisos_totais.extend(avisos_item)

    texto_completo = "\n\n".join(blocos)

    # Resolve as tags de concordancia «palavra:grupo» (usadas em minutas
    # que tratam gênero/número de outorgante, outorgado e imóvel de forma
    # explicita) -- feito no texto ja' montado, DEPOIS de resolver
    # variantes/sub-itens, porque as tags sao texto simples (nao usam a
    # sintaxe {{ }}) e nao interferem em nada da montagem anterior.
    outorgantes = contexto.get("outorgantes") or ([contexto["outorgante"]] if contexto.get("outorgante") else [])
    outorgados = contexto.get("outorgados") or ([contexto["outorgado"]] if contexto.get("outorgado") else [])
    qtd_imoveis = len(contexto.get("imoveis") or [1])  # multi-imovel ainda nao esta' cadastrado em todo lugar -- default 1
    concordancia_por_grupo = {
        1: calcular_concordancia_grupo(outorgantes),
        2: calcular_concordancia_grupo(outorgados),
        4: calcular_concordancia_quantidade(qtd_imoveis),
    }
    texto_completo, avisos_concordancia = resolver_concordancia(texto_completo, concordancia_por_grupo)
    avisos_totais.extend(avisos_concordancia)

    return texto_completo, avisos_totais


def listar_modelos_disponiveis() -> dict:
    """Retorna {tipo_ato_id: nome} dos modelos que ja tem itens
    cadastrados -- usado pra saber quais tipos de ato ja podem gerar
    minuta de verdade, sem precisar abrir o JSON na mao."""
    dados = _carregar_dados()
    return {tid: m["nome"] for tid, m in dados["modelos"].items()}


def _salvar_dados(dados: dict) -> None:
    with open(CAMINHO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def obter_modelo(tipo_ato: str) -> dict:
    """Devolve o modelo inteiro (nome, itens, ordem) de um tipo de ato --
    usado pela tela de Configuracoes pra listar/editar."""
    dados = _carregar_dados()
    if tipo_ato not in dados["modelos"]:
        raise ValueError(f"Tipo de ato '{tipo_ato}' não encontrado.")
    return dados["modelos"][tipo_ato]


def criar_modelo(tipo_ato: str, nome: str) -> None:
    """Cria um tipo de ato novo, vazio (sem itens ainda) -- o botao
    '+ Adicionar/configurar nova minuta' da tela de Configuracoes."""
    dados = _carregar_dados()
    if tipo_ato in dados["modelos"]:
        raise ValueError(f"Já existe um modelo com o id '{tipo_ato}'.")
    dados["modelos"][tipo_ato] = {"nome": nome, "itens": {}, "ordem": []}
    _salvar_dados(dados)


def salvar_item(tipo_ato: str, item_id: str, item: dict, adicionar_a_ordem: bool = True) -> None:
    """Cria ou atualiza um item dentro de um modelo. 'item' precisa ter
    pelo menos 'nome' e 'texto_padrao'; 'variantes' e' opcional (lista)."""
    dados = _carregar_dados()
    if tipo_ato not in dados["modelos"]:
        raise ValueError(f"Tipo de ato '{tipo_ato}' não encontrado.")

    modelo = dados["modelos"][tipo_ato]
    item.setdefault("variantes", [])
    modelo["itens"][item_id] = item

    if adicionar_a_ordem and item_id not in modelo["ordem"]:
        modelo["ordem"].append(item_id)

    _salvar_dados(dados)


def remover_item(tipo_ato: str, item_id: str) -> None:
    dados = _carregar_dados()
    if tipo_ato not in dados["modelos"]:
        raise ValueError(f"Tipo de ato '{tipo_ato}' não encontrado.")
    modelo = dados["modelos"][tipo_ato]
    modelo["itens"].pop(item_id, None)
    modelo["ordem"] = [i for i in modelo["ordem"] if i != item_id]
    _salvar_dados(dados)


def salvar_ordem(tipo_ato: str, nova_ordem: list[str]) -> None:
    """Redefine a ordem de composicao de um modelo. Precisa conter
    exatamente os mesmos ids que ja existem em 'itens' (nem mais, nem
    menos) -- protege contra referenciar item que nao existe."""
    dados = _carregar_dados()
    if tipo_ato not in dados["modelos"]:
        raise ValueError(f"Tipo de ato '{tipo_ato}' não encontrado.")
    modelo = dados["modelos"][tipo_ato]

    invalidos = [i for i in nova_ordem if i not in modelo["itens"]]
    if invalidos:
        raise ValueError(f"Itens inexistentes na nova ordem: {invalidos}")

    modelo["ordem"] = nova_ordem
    _salvar_dados(dados)
