"""
Resolve as tags de concordancia gramatical «palavra:grupo» usadas no
template real de minuta do usuario -- coisas como «VENDEDOR:1» virando
"VENDEDOR"/"VENDEDORA"/"VENDEDORES"/"VENDEDORAS" dependendo de quantas
pessoas tem no grupo 1 (outorgante) e qual o genero de cada uma.

COMO FUNCIONA (importante entender antes de mexer):

Cada grupo numerado corresponde a uma entidade do caso:
  grupo 1 = outorgante(s) (vendedor)
  grupo 2 = outorgado(s) (comprador)
  grupo 4 = imovel(is) / documentos relacionados a ele (matricula, certidao
            municipal, guias) -- aqui o GENERO de cada palavra e' FIXO
            (ja vem certo no proprio texto, porque "imovel" e' sempre
            masculino mas "matricula"/"certidao" sao sempre femininos --
            o autor do template ja escreveu a palavra no genero certo),
            SO' o NUMERO varia (singular/plural conforme a quantidade de
            imoveis no caso).

Por isso cada palavra cadastrada em PALAVRAS_GRUPO_PESSOA precisa das 4
formas (masculino singular/plural, feminino singular/plural), enquanto
palavras em PALAVRAS_GRUPO_NEUTRO (usadas nos grupos 1, 2 quando a
palavra em si tem genero fixo -- ex: 'certidao' sempre feminino mesmo
falando do outorgante -- e SEMPRE no grupo 4) so' precisam de singular/
plural, sem variar genero.

NAO e' um "adivinhador" generico de plural/genero em portugues -- e' uma
tabela EXPLICITA, palavra por palavra, com as formas escritas a mao. Isso
e' proposital: um adivinhador automatico erraria plural irregular (bem
-> bens, imovel -> imoveis, certidao -> certidoes) com risco real de sair
errado numa escritura publica assinada. Cadastrar a palavra uma vez so'
e' mais trabalho, mas e' seguro -- se aparecer uma palavra nova tagueada
que nao esteja na tabela, o sistema avisa em vez de arriscar um palpite.
"""
import re


# ---------------------------------------------------------------------------
# TABELA DE PALAVRAS -- grupo 1 (outorgante) e grupo 2 (outorgado): pessoa,
# precisa de genero E numero. Chave e' a palavra EXATAMENTE como aparece
# dentro de «» no template (maiuscula/minuscula importam, pra preservar o
# estilo de capitalizacao que o autor escolheu em cada trecho).
# ---------------------------------------------------------------------------
PALAVRAS_PESSOA = {
    # -- comuns aos dois grupos (repetidas em ambos por clareza) --
    "O": {"ms": "O", "fs": "A", "mp": "OS", "fp": "AS"},
    "DO": {"ms": "DO", "fs": "DA", "mp": "DOS", "fp": "DAS"},
    "pelo": {"ms": "pelo", "fs": "pela", "mp": "pelos", "fp": "pelas"},
    "Pelo": {"ms": "Pelo", "fs": "Pela", "mp": "Pelos", "fp": "Pelas"},
    "declara": {"ms": "declara", "fs": "declara", "mp": "declaram", "fp": "declaram"},
    "faz": {"ms": "faz", "fs": "faz", "mp": "fazem", "fp": "fazem"},
    "Declara": {"ms": "Declara", "fs": "Declara", "mp": "Declaram", "fp": "Declaram"},

    # -- grupo 1 (outorgante / vendedor) --
    "OUTORGANTE": {"ms": "OUTORGANTE", "fs": "OUTORGANTE", "mp": "OUTORGANTES", "fp": "OUTORGANTES"},
    "outorgante": {"ms": "outorgante", "fs": "outorgante", "mp": "outorgantes", "fp": "outorgantes"},
    "VENDEDOR": {"ms": "VENDEDOR", "fs": "VENDEDORA", "mp": "VENDEDORES", "fp": "VENDEDORAS"},
    "é": {"ms": "é", "fs": "é", "mp": "são", "fp": "são"},
    "senhor": {"ms": "senhor", "fs": "senhora", "mp": "senhores", "fp": "senhoras"},
    "legítimo": {"ms": "legítimo", "fs": "legítima", "mp": "legítimos", "fp": "legítimas"},
    "possuidor": {"ms": "possuidor", "fs": "possuidora", "mp": "possuidores", "fp": "possuidoras"},
    "empregador": {"ms": "empregador", "fs": "empregadora", "mp": "empregadores", "fp": "empregadoras"},
    "rural": {"ms": "rural", "fs": "rural", "mp": "rurais", "fp": "rurais"},
    "urbano": {"ms": "urbano", "fs": "urbana", "mp": "urbanos", "fp": "urbanas"},
    "deixa": {"ms": "deixa", "fs": "deixa", "mp": "deixam", "fp": "deixam"},
    "encontra": {"ms": "encontra", "fs": "encontra", "mp": "encontram", "fp": "encontram"},
    "assume": {"ms": "assume", "fs": "assume", "mp": "assumem", "fp": "assumem"},
    "VENDE": {"ms": "VENDE", "fs": "VENDE", "mp": "VENDEM", "fp": "VENDEM"},
    "confessa": {"ms": "confessa", "fs": "confessa", "mp": "confessam", "fp": "confessam"},
    "dá": {"ms": "dá", "fs": "dá", "mp": "dão", "fp": "dão"},
    "transfere": {"ms": "transfere", "fs": "transfere", "mp": "transferem", "fp": "transferem"},
    "confere": {"ms": "confere", "fs": "confere", "mp": "conferem", "fp": "conferem"},

    # -- grupo 2 (outorgado / comprador) --
    "OUTORGADO": {"ms": "OUTORGADO", "fs": "OUTORGADA", "mp": "OUTORGADOS", "fp": "OUTORGADAS"},
    "Outorgado": {"ms": "Outorgado", "fs": "Outorgada", "mp": "Outorgados", "fp": "Outorgadas"},
    "COMPRADOR": {"ms": "COMPRADOR", "fs": "COMPRADORA", "mp": "COMPRADORES", "fp": "COMPRADORAS"},
    "do": {"ms": "do", "fs": "da", "mp": "dos", "fp": "das"},
    "ao": {"ms": "ao", "fs": "à", "mp": "aos", "fp": "às"},
    "o": {"ms": "o", "fs": "a", "mp": "os", "fp": "as"},
    "mesmo": {"ms": "mesmo", "fs": "mesma", "mp": "mesmos", "fp": "mesmas"},
    "use": {"ms": "use", "fs": "use", "mp": "usem", "fp": "usem"},
    "goze": {"ms": "goze", "fs": "goze", "mp": "gozem", "fp": "gozem"},
    "disponha": {"ms": "disponha", "fs": "disponha", "mp": "disponham", "fp": "disponham"},
    "aceita": {"ms": "aceita", "fs": "aceita", "mp": "aceitam", "fp": "aceitam"},
    "foi": {"ms": "foi", "fs": "foi", "mp": "foram", "fp": "foram"},
    "orientado": {"ms": "orientado", "fs": "orientada", "mp": "orientados", "fp": "orientadas"},
    "dispensa": {"ms": "dispensa", "fs": "dispensa", "mp": "dispensam", "fp": "dispensam"},

    # -- novas (Doação, Dação em Pagamento) -- cadastradas depois de ler os
    # 7 modelos de referencia e rodar o resolver de verdade contra eles,
    # coletando cada "Palavra de concordancia desconhecida" que apareceu.
    "DOADOR": {"ms": "DOADOR", "fs": "DOADORA", "mp": "DOADORES", "fp": "DOADORAS"},
    "Doador": {"ms": "Doador", "fs": "Doadora", "mp": "Doadores", "fp": "Doadoras"},
    "doador": {"ms": "doador", "fs": "doadora", "mp": "doadores", "fp": "doadoras"},
    "DONATÁRIO": {"ms": "DONATÁRIO", "fs": "DONATÁRIA", "mp": "DONATÁRIOS", "fp": "DONATÁRIAS"},
    "Donatário": {"ms": "Donatário", "fs": "Donatária", "mp": "Donatários", "fp": "Donatárias"},
    "donatário": {"ms": "donatário", "fs": "donatária", "mp": "donatários", "fp": "donatárias"},
    "DEVEDOR": {"ms": "DEVEDOR", "fs": "DEVEDORA", "mp": "DEVEDORES", "fp": "DEVEDORAS"},
    "devedor": {"ms": "devedor", "fs": "devedora", "mp": "devedores", "fp": "devedoras"},
    "CREDOR": {"ms": "CREDOR", "fs": "CREDORA", "mp": "CREDORES", "fp": "CREDORAS"},
    # variantes de capitalizacao de palavras que ja existiam so' numa forma
    "Outorgante": {"ms": "Outorgante", "fs": "Outorgante", "mp": "Outorgantes", "fp": "Outorgantes"},
    "outorgado": {"ms": "outorgado", "fs": "outorgada", "mp": "outorgados", "fp": "outorgadas"},
    "vendedor": {"ms": "vendedor", "fs": "vendedora", "mp": "vendedores", "fp": "vendedoras"},
    "Vendedor": {"ms": "Vendedor", "fs": "Vendedora", "mp": "Vendedores", "fp": "Vendedoras"},
    "comprador": {"ms": "comprador", "fs": "compradora", "mp": "compradores", "fp": "compradoras"},
    "Comprador": {"ms": "Comprador", "fs": "Compradora", "mp": "Compradores", "fp": "Compradoras"},
    "Notificado": {"ms": "Notificado", "fs": "Notificada", "mp": "Notificados", "fp": "Notificadas"},
    # verbos (3a pessoa) -- a maioria nao varia por genero em portugues,
    # so' por numero, mas funciona igual cadastrado aqui (ms=fs, mp=fp)
    "doa": {"ms": "doa", "fs": "doa", "mp": "doam", "fp": "doam"},
    "reserva": {"ms": "reserva", "fs": "reserva", "mp": "reservam", "fp": "reservam"},
    "obriga": {"ms": "obriga", "fs": "obriga", "mp": "obrigam", "fp": "obrigam"},
    "passe": {"ms": "passe", "fs": "passe", "mp": "passem", "fp": "passem"},
    "exercia": {"ms": "exercia", "fs": "exercia", "mp": "exerciam", "fp": "exerciam"},
    "achava": {"ms": "achava", "fs": "achava", "mp": "achavam", "fp": "achavam"},
    "comercializava": {"ms": "comercializava", "fs": "comercializava", "mp": "comercializavam", "fp": "comercializavam"},
    "exportava": {"ms": "exportava", "fs": "exportava", "mp": "exportavam", "fp": "exportavam"},
    "vendia": {"ms": "vendia", "fs": "vendia", "mp": "vendiam", "fp": "vendiam"},
    "tornou": {"ms": "tornou", "fs": "tornou", "mp": "tornaram", "fp": "tornaram"},
    "deixou": {"ms": "deixou", "fs": "deixou", "mp": "deixaram", "fp": "deixaram"},
    "transmite": {"ms": "transmite", "fs": "transmite", "mp": "transmitem", "fp": "transmitem"},
    "monta": {"ms": "monta", "fs": "monta", "mp": "montam", "fp": "montam"},
    "abrange": {"ms": "abrange", "fs": "abrange", "mp": "abrangem", "fp": "abrangem"},
    "for": {"ms": "for", "fs": "for", "mp": "forem", "fp": "forem"},
    "poderá": {"ms": "poderá", "fs": "poderá", "mp": "poderão", "fp": "poderão"},
    "terá": {"ms": "terá", "fs": "terá", "mp": "terão", "fp": "terão"},
    "tinha": {"ms": "tinha", "fs": "tinha", "mp": "tinham", "fp": "tinham"},
    "responderá": {"ms": "responderá", "fs": "responderá", "mp": "responderão", "fp": "responderão"},
    "possui": {"ms": "possui", "fs": "possui", "mp": "possuem", "fp": "possuem"},
    # adjetivos/particípios com flexao de genero de verdade
    "falecido": {"ms": "falecido", "fs": "falecida", "mp": "falecidos", "fp": "falecidas"},
    "vivo": {"ms": "vivo", "fs": "viva", "mp": "vivos", "fp": "vivas"},
    "vendido": {"ms": "vendido", "fs": "vendida", "mp": "vendidos", "fp": "vendidas"},
    "doado": {"ms": "doado", "fs": "doada", "mp": "doados", "fp": "doadas"},
    "dado": {"ms": "dado", "fs": "dada", "mp": "dados", "fp": "dadas"},
    "dito": {"ms": "dito", "fs": "dita", "mp": "ditos", "fp": "ditas"},
    "aludido": {"ms": "aludido", "fs": "aludida", "mp": "aludidos", "fp": "aludidas"},
    "mencionado": {"ms": "mencionado", "fs": "mencionada", "mp": "mencionados", "fp": "mencionadas"},
    "referido": {"ms": "referido", "fs": "referida", "mp": "referidos", "fp": "referidas"},
    "descrito": {"ms": "descrito", "fs": "descrita", "mp": "descritos", "fp": "descritas"},
    "desembaraçado": {"ms": "desembaraçado", "fs": "desembaraçada", "mp": "desembaraçados", "fp": "desembaraçadas"},
    "havido": {"ms": "havido", "fs": "havida", "mp": "havidos", "fp": "havidas"},
    "emitido": {"ms": "emitido", "fs": "emitida", "mp": "emitidos", "fp": "emitidas"},
    "quitado": {"ms": "quitado", "fs": "quitada", "mp": "quitados", "fp": "quitadas"},
    "recolhida": {"ms": "recolhido", "fs": "recolhida", "mp": "recolhidos", "fp": "recolhidas"},
    "vinculado": {"ms": "vinculado", "fs": "vinculada", "mp": "vinculados", "fp": "vinculadas"},
    "sujeito": {"ms": "sujeito", "fs": "sujeita", "mp": "sujeitos", "fp": "sujeitas"},
    "respectiva": {"ms": "respectivo", "fs": "respectiva", "mp": "respectivos", "fp": "respectivas"},
    "constituinte": {"ms": "constituinte", "fs": "constituinte", "mp": "constituintes", "fp": "constituintes"},
    "responsável": {"ms": "responsável", "fs": "responsável", "mp": "responsáveis", "fp": "responsáveis"},
    "constante": {"ms": "constante", "fs": "constante", "mp": "constantes", "fp": "constantes"},
    "seguinte": {"ms": "seguinte", "fs": "seguinte", "mp": "seguintes", "fp": "seguintes"},
    "livre": {"ms": "livre", "fs": "livre", "mp": "livres", "fp": "livres"},
    # pronomes e artigos combinados com flexao de genero
    "este": {"ms": "este", "fs": "esta", "mp": "estes", "fp": "estas"},
    "ele": {"ms": "ele", "fs": "ela", "mp": "eles", "fp": "elas"},
    "dele": {"ms": "dele", "fs": "dela", "mp": "deles", "fp": "delas"},
    "cuja": {"ms": "cujo", "fs": "cuja", "mp": "cujos", "fp": "cujas"},
    "da": {"ms": "do", "fs": "da", "mp": "dos", "fp": "das"},
    "no": {"ms": "no", "fs": "na", "mp": "nos", "fp": "nas"},
    "lhe": {"ms": "lhe", "fs": "lhe", "mp": "lhes", "fp": "lhes"},
    # substantivos invariantes por genero (so' o numero muda) -- a tag so'
    # existe pra cobrir o caso de precisar virar plural, nao pra mudar sexo
    "código": {"ms": "código", "fs": "código", "mp": "códigos", "fp": "códigos"},
    "cópia": {"ms": "cópia", "fs": "cópia", "mp": "cópias", "fp": "cópias"},
    "protocolo": {"ms": "protocolo", "fs": "protocolo", "mp": "protocolos", "fp": "protocolos"},
    "guia": {"ms": "guia", "fs": "guia", "mp": "guias", "fp": "guias"},
    "vem": {"ms": "vem", "fs": "vem", "mp": "vêm", "fp": "vêm"},
    "Conjunta": {"ms": "Conjunto", "fs": "Conjunta", "mp": "Conjuntos", "fp": "Conjuntas"},
}

# ---------------------------------------------------------------------------
# TABELA DE PALAVRAS -- genero FIXO, so' varia singular/plural. Usada pelo
# grupo 4 (imovel/matricula/certidao) inteiro, e por algumas palavras dos
# grupos 1/2 que descrevem um substantivo de genero fixo (ex: 'certidao'
# no grupo 1 -- e' sempre feminino, so' pluraliza se tiver mais de um
# outorgante precisando apresentar uma certidao cada).
# ---------------------------------------------------------------------------
PALAVRAS_NUMERO_FIXO = {
    "IMÓVEL": {"s": "IMÓVEL", "p": "IMÓVEIS"},
    "imóvel": {"s": "imóvel", "p": "imóveis"},
    "vendido": {"s": "vendido", "p": "vendidos"},
    "qual": {"s": "qual", "p": "quais"},
    "esta": {"s": "está", "p": "estão"},  # corrige acentuacao (typo comum: "esta" -> "está")
    "livre": {"s": "livre", "p": "livres"},
    "desembaraçado": {"s": "desembaraçado", "p": "desembaraçados"},
    "possui": {"s": "possui", "p": "possuem"},
    "Certidão": {"s": "Certidão", "p": "Certidões"},
    "Negativa": {"s": "Negativa", "p": "Negativas"},
    "nº": {"s": "nº", "p": "nºs"},
    "emitida": {"s": "emitida", "p": "emitidas"},
    "descrito": {"s": "descrito", "p": "descritos"},
    "BEM": {"s": "BEM", "p": "BENS"},
    "objeto": {"s": "objeto", "p": "objetos"},
    "matrícula": {"s": "matrícula", "p": "matrículas"},
    "mencionada": {"s": "mencionada", "p": "mencionadas"},
    "consolidará": {"s": "consolidará", "p": "consolidarão"},
    "seu": {"s": "seu", "p": "seus"},
    "fica": {"s": "fica", "p": "ficam"},
    "expedida": {"s": "expedida", "p": "expedidas"},
    "a": {"s": "a", "p": "as"},
    "arquivada": {"s": "arquivada", "p": "arquivadas"},
    "Guia": {"s": "Guia", "p": "Guias"},
    "quitada": {"s": "quitada", "p": "quitadas"},
    # usadas no grupo 1, mas com genero fixo feminino (independem do
    # genero da pessoa -- "certidao" e' sempre feminina):
    "certidão": {"s": "certidão", "p": "certidões"},
    "válida": {"s": "válida", "p": "válidas"},
    "relativa": {"s": "relativa", "p": "relativas"},
}


def _limpar_para_genero(texto: str) -> str:
    """Remove residuo tipo '(a)'/'(o)' antes de checar o final da
    palavra -- camada de defesa extra, caso a IA ainda devolva algo tipo
    'brasileiro(a)' apesar da instrucao do schema pedir uma forma so'."""
    texto = texto.strip().lower()
    for sufixo in ["(a)", "(o)", "(as)", "(os)"]:
        if texto.endswith(sufixo):
            texto = texto[: -len(sufixo)]
    return texto.strip()


def inferir_genero(pessoa: dict) -> str:
    """Infere 'm' ou 'f'. Prioridade: campo 'sexo' EXPLICITO primeiro (vem
    impresso literalmente no RG/CNH como 'M'/'F' -- o sinal mais confiavel
    que existe, porque nao depende de nenhuma inferencia de texto).
    Historico do bug que motivou essa mudanca: o sistema so' tinha os
    sinais de texto abaixo (nacionalidade/estado_civil); numa geracao
    real, a nacionalidade de uma outorgante mulher nao veio devidamente
    generizada na extracao daquela chamada especifica, e o sistema
    escreveu 'seu marido' pra ela na escritura -- um erro grave, evitavel,
    porque o proprio documento ja' dizia 'Sexo: F' com todas as letras.

    Se 'sexo' nao vier preenchido (documento sem esse campo, ou uma
    chamada anterior a essa mudanca), cai pros sinais antigos como
    fallback: nacionalidade primeiro (quase sempre generizada no RG --
    'brasileiro'/'brasileira'), depois estado_civil (tambem generizado em
    portugues: casado/casada, solteiro/solteira etc.). Se nao der pra
    inferir de nenhum dos tres, assume 'm' -- fallback de ultimo caso,
    nunca deveria realmente acontecer com dado extraido normalmente."""
    sexo = (pessoa.get("sexo") or "").strip().upper()
    if sexo in ("M", "F"):
        return sexo.lower()

    # Pessoa juridica: nao tem 'sexo' nem 'nacionalidade'. Na pratica
    # notarial a empresa e' tratada no feminino ("a outorgante vendedora,
    # na forma representada") -- sem isso caia no fallback masculino e a
    # minuta saia "o outorgante vendedor ... senhor e legitimo possuidor".
    if pessoa.get("_tipo") == "PJ":
        return "f"

    nacionalidade = _limpar_para_genero(pessoa.get("nacionalidade") or "")
    if nacionalidade.endswith("a"):
        return "f"
    if nacionalidade.endswith("o"):
        return "m"
    estado_civil = _limpar_para_genero(pessoa.get("estado_civil") or "")
    if estado_civil.endswith("a"):
        return "f"
    return "m"


def enriquecer_pessoa_com_concordancia(pessoa: dict, incluir_regime_bens: bool = True, incluir_endereco: bool = True) -> dict:
    """Devolve uma COPIA da pessoa com campos extras de concordancia
    INDIVIDUAL (do genero dessa pessoa especifica) -- usado dentro de
    blocos de repeticao tipo {{#outorgantes}}...{{/outorgantes}} pra
    qualificacao ('portador do RG' vs 'portadora do RG'), onde cada
    pessoa listada tem seu proprio genero -- diferente das tags
    «palavra:N», que resolvem pelo genero AGREGADO do grupo inteiro
    (usadas em frases tipo 'O OUTORGANTE declara', que fala do grupo
    como um todo, nao de uma pessoa especifica dentro dele).

    'incluir_regime_bens=False' pula a clausula de conjuge/regime mesmo
    se a pessoa for casada -- usado pro PROCURADOR, cuja qualificacao
    convencionalmente so' cita o estado civil simples ('casado'), sem
    nome do conjuge nem regime, ja' que ele nao e' parte no negocio, so'
    representa quem e'.

    Tambem monta 'texto_qualificacao' -- a clausula de qualificacao
    completa e pronta, ja' escolhendo o formato certo (PF ou PJ). Se for
    PJ com representante, o representante e' enriquecido recursivamente
    (so' um nivel -- representante nunca tem representante proprio)."""
    genero = inferir_genero(pessoa)
    estado_civil = (pessoa.get("estado_civil") or "").strip().lower()
    extras = {
        "portador_a": "portador" if genero == "m" else "portadora",
        "inscrito_a": "inscrito" if genero == "m" else "inscrita",
        "residente_domiciliado_a": "residente e domiciliado" if genero == "m" else "residente e domiciliada",
    }
    if estado_civil.startswith("casad") and incluir_regime_bens:
        nome_conjuge = pessoa.get("nome_conjuge") or "[FALTA: nome_conjuge]"
        regime = pessoa.get("regime_bens") or "[FALTA: regime_bens]"
        palavra_casado = "casado" if genero == "m" else "casada"
        extras["clausula_regime_bens"] = f", {palavra_casado} com {nome_conjuge}, sob o regime de {regime}"
    else:
        extras["clausula_regime_bens"] = ""

    pessoa_enriquecida = {**pessoa, **extras}

    # Alias -- PJ usa 'razao_social', nao 'nome', mas varios trechos do
    # texto (ex: o cabecalho "que faz: {{nome}}") usam {{nome}} de forma
    # generica pra qualquer tipo de outorgante/outorgado. Sem isso, PJ
    # sempre aparecia como [FALTA: nome] nesses pontos.
    if pessoa_enriquecida.get("_tipo") == "PJ" and not pessoa_enriquecida.get("nome"):
        pessoa_enriquecida["nome"] = pessoa_enriquecida.get("razao_social")

    if pessoa.get("_tipo") == "PJ" and pessoa.get("representante"):
        pessoa_enriquecida["representante"] = enriquecer_pessoa_com_concordancia(pessoa["representante"])

    if pessoa.get("representado_por_procurador") and pessoa.get("procurador"):
        pessoa_enriquecida["procurador"] = enriquecer_pessoa_com_concordancia(pessoa["procurador"], incluir_regime_bens=False)

    # Conjuge participante (vende tambem / anui) -- ver
    # _fundir_qualificacao_conjugal logo abaixo pro racional completo.
    conjuge_info = pessoa.get("conjuge_participante")
    fundir_conjuge = bool(
        conjuge_info and conjuge_info.get("participacao") in ("outorga_tambem", "anui") and conjuge_info.get("dados")
    )

    # Flag que _bloco_estado_civil le pra decidir se monta a clausula
    # completa de regime/certidao (comportamento normal, default True) ou
    # so' a palavra simples (procurador, ou titular cujo conjuge esta'
    # sendo fundido na mesma qualificacao -- nesse ultimo caso a clausula
    # de regime some da qualificacao INDIVIDUAL porque vai aparecer, uma
    # unica vez, na frase fundida).
    pessoa_enriquecida["_incluir_regime_bens"] = incluir_regime_bens and not fundir_conjuge
    pessoa_enriquecida["_incluir_endereco"] = incluir_endereco

    if fundir_conjuge:
        # Endereco compartilhado: se os dois moram no MESMO lugar (caso
        # mais comum -- casal residindo junto), a clausula de endereco
        # tambem sai da qualificacao INDIVIDUAL de cada um e vai citada
        # UMA UNICA VEZ no final da frase fundida, igual ja' acontece com
        # o regime de bens. Se os enderecos forem DIFERENTES, cada um
        # mantem o proprio endereco na qualificacao individual (nao
        # funde nesse caso -- seria informacao perdida).
        mesmo_endereco = _normalizar_para_comparar(pessoa.get("endereco")) == _normalizar_para_comparar(
            conjuge_info["dados"].get("endereco")
        ) and bool(pessoa.get("endereco"))

        conjuge_enriquecido = enriquecer_pessoa_com_concordancia(
            conjuge_info["dados"], incluir_regime_bens=False, incluir_endereco=not mesmo_endereco
        )
        pessoa_enriquecida["_incluir_endereco"] = not mesmo_endereco
        texto_titular = _construir_texto_qualificacao(pessoa_enriquecida)
        pessoa_enriquecida["texto_qualificacao"] = _fundir_qualificacao_conjugal(
            texto_titular, conjuge_enriquecido, pessoa_enriquecida, conjuge_info.get("participacao"),
            endereco_comum=pessoa.get("endereco") if mesmo_endereco else None,
        )
        pessoa_enriquecida["conjuge_enriquecido"] = conjuge_enriquecido
        # conta como 2 pessoas pra concordancia de numero do grupo (ex:
        # "OS OUTORGANTES VENDEDORES"), mesmo sendo UMA entrada na lista.
        pessoa_enriquecida["_peso_concordancia"] = 2
    else:
        pessoa_enriquecida["texto_qualificacao"] = _construir_texto_qualificacao(pessoa_enriquecida)

    return pessoa_enriquecida


def _normalizar_para_comparar(texto: str | None) -> str:
    """Normalizacao leve (minusculo, espacos colapsados, sem acento nos
    espacos) pra comparar dois enderecos e decidir se sao 'o mesmo lugar'
    apesar de pequenas diferencas de digitacao/formatacao entre o que foi
    lido do documento do titular e do conjuge."""
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip().lower()


_RAIZES_ESTADO_CIVIL = ["solteir", "casad", "divorciad", "viuv", "separad"]


def _normalizar_estado_civil(estado_civil_bruto: str, genero: str) -> str:
    """Independente do que a extracao devolveu (com ou sem '(a)', em
    maiuscula, ou ocasionalmente com o sufixo trocado), recalcula a
    palavra certa a partir da RAIZ do estado civil + do genero CONFIAVEL
    (ver inferir_genero, que agora prioriza o campo 'sexo' explicito) --
    nunca confia cegamente no sufixo que veio da extracao. Camada de
    defesa extra: mesmo que a instrucao do schema falhe ou a IA erre um
    dia, o sufixo final sempre bate com o genero real da pessoa.
    Ex.: 'casado(a)', 'CASADO' ou 'casada' todos viram 'casada' se
    genero == 'f'."""
    bruto = estado_civil_bruto.strip().lower()
    for sufixo in ["(a)", "(o)"]:
        bruto = bruto.replace(sufixo, "")
    bruto = bruto.strip()
    for raiz in _RAIZES_ESTADO_CIVIL:
        if bruto.startswith(raiz):
            return raiz + ("a" if genero == "f" else "o")
    return bruto  # raiz desconhecida (nao deveria acontecer) -- devolve como veio


def _bloco_estado_civil(pessoa_enriquecida: dict) -> str:
    """Monta o trecho de estado civil completo -- palavra + (se tiver
    certidao enviada) a citacao dela + declaracao de nao uniao estavel
    quando aplicavel. Cobre os 5 estados civis (solteiro, casado,
    divorciado, viuvo, separado). Sem certidao enviada, fica so' na
    palavra simples (comportamento antigo, pra nao forcar [FALTA] no
    caso comum de declaracao manual sem documento)."""
    estado_civil_bruto = (pessoa_enriquecida.get("estado_civil") or "").strip()
    if not estado_civil_bruto:
        return ", [FALTA: estado_civil]"
    estado_civil = _normalizar_estado_civil(estado_civil_bruto, inferir_genero(pessoa_enriquecida))

    # Quando incluir_regime_bens=False (procurador, ou titular cujo
    # conjuge esta' sendo fundido numa qualificacao conjunta -- ver
    # enriquecer_pessoa_com_concordancia), a convencao e' citar so' a
    # palavra do estado civil, sem nome do conjuge/regime/certidao --
    # essa informacao ou nao interessa (procurador so' representa, nao e'
    # parte) ou vai aparecer uma unica vez na frase fundida, nao aqui.
    incluir_regime_bens = pessoa_enriquecida.get("_incluir_regime_bens", True)
    if estado_civil.startswith("casad") and not incluir_regime_bens:
        return f", {estado_civil}"

    numero_cert = pessoa_enriquecida.get("numero_certidao_estado_civil")
    data_emissao_cert = pessoa_enriquecida.get("data_emissao_certidao_estado_civil")
    cartorio_cert = pessoa_enriquecida.get("cartorio_certidao_estado_civil")
    tem_certidao = bool(numero_cert)

    if estado_civil.startswith("casad"):
        conjuge = pessoa_enriquecida.get("nome_conjuge") or "[FALTA: nome_conjuge]"
        regime = pessoa_enriquecida.get("regime_bens") or "[FALTA: regime_bens]"
        data_casamento = pessoa_enriquecida.get("data_casamento")
        texto = f", {estado_civil} com {conjuge}, sob o regime de {regime}"
        if data_casamento:
            texto += f", aos {data_casamento}"
        if tem_certidao:
            texto += (
                f", conforme certidão de casamento matriculada sob nº {numero_cert}, "
                f"emitida em {data_emissao_cert or '[FALTA: data_emissao_certidao_estado_civil]'}, "
                f"pelo {cartorio_cert or '[FALTA: cartorio_certidao_estado_civil]'}"
            )
        return texto

    if not tem_certidao:
        # sem certidao enviada -- fica so' na palavra simples, sem forcar
        # [FALTA] no caso comum de declaracao manual sem documento
        return f", {estado_civil}"

    # nao-casado (solteiro, divorciado, viuvo, separado) COM certidao
    # enviada -- cada tipo cita a certidao com a redacao propria
    descricao_por_tipo = {
        "solteiro": ("Certidão de Nascimento, extraída da Matrícula", "nº"),
        "solteira": ("Certidão de Nascimento, extraída da Matrícula", "nº"),
        "divorciado": ("Certidão de Casamento com Averbação de Divórcio matriculada", "sob nº"),
        "divorciada": ("Certidão de Casamento com Averbação de Divórcio matriculada", "sob nº"),
        "viúvo": ("Certidão de Casamento com Averbação de Óbito matriculada", "sob nº"),
        "viúva": ("Certidão de Casamento com Averbação de Óbito matriculada", "sob nº"),
        "separado": ("Certidão de Casamento com Averbação de Separação matriculada", "sob nº"),
        "separada": ("Certidão de Casamento com Averbação de Separação matriculada", "sob nº"),
    }
    descricao, conector_numero = descricao_por_tipo.get(estado_civil, ("certidão", "sob nº"))
    return (
        f", {estado_civil}, conforme {descricao} {conector_numero} {numero_cert}, "
        f"em {data_emissao_cert or '[FALTA: data_emissao_certidao_estado_civil]'}, "
        f"pelo {cartorio_cert or '[FALTA: cartorio_certidao_estado_civil]'}, "
        f"declarando ainda não conviver em união estável"
    )


def _nome_negrito_maiusculo(pessoa_enriquecida: dict) -> str:
    """Devolve o nome da PESSOA FISICA em negrito e maiusculo, no formato
    que a docx skill interpreta (**...**) -- convencao pedida pro usuario
    pra toda escritura: nomes das partes sempre em negrito e maiusculo na
    qualificacao. So' se aplica a PF (razao_social de PJ fica normal,
    convencao usual de escritura nao versaliza nome de empresa)."""
    nome = pessoa_enriquecida.get("nome") or "[FALTA: nome]"
    return f"**{nome.upper()}**"


def _construir_texto_qualificacao(pessoa_enriquecida: dict) -> str:
    """Monta a frase de qualificacao completa -- chamado DEPOIS que a
    pessoa ja' passou por enriquecer_pessoa_com_concordancia (precisa dos
    campos extras ja' calculados: portador_a, clausula_regime_bens etc.)."""
    def campo(chave):
        return pessoa_enriquecida.get(chave) or f"[FALTA: {chave}]"

    if pessoa_enriquecida.get("_tipo") == "PJ":
        nire_txt = f", com Número de Identificação do Registro de Empresas - NIRE nº {pessoa_enriquecida['nire']}" \
            if pessoa_enriquecida.get("nire") else ""
        representante = pessoa_enriquecida.get("representante")
        texto_rep = _construir_texto_qualificacao(representante) if representante else "[FALTA: representante]"
        return (
            f"{campo('razao_social')}, pessoa jurídica de direito privado, com sede em "
            f"{campo('endereco_sede')}, inscrita no CNPJ/MF sob nº {campo('cnpj')}{nire_txt}, "
            f"neste ato representada por {texto_rep}, nos termos do Contrato Social, a qual "
            f"encontra-se devidamente registrado na Junta Comercial do {campo('uf_junta_comercial')} "
            f"sob nº {campo('numero_registro_junta')} em data de {campo('data_registro_junta')}, a qual "
            f"fica cópia arquivada nesta Serventia às fls. {campo('fls_arquivo_contrato')} do livro "
            f"{campo('livro_arquivo_contrato')}-B, e Certidão Simplificada expedida pela Junta Comercial "
            f"do {campo('uf_junta_comercial')} em data de {campo('data_certidao_simplificada')}, a qual "
            f"fica arquivada nesta Serventia às fls. {campo('fls_arquivo_simplificada')} do livro "
            f"{campo('livro_arquivo_simplificada')}-B"
        )

    natural_txt = f", natural de {campo('naturalidade')}" if pessoa_enriquecida.get("naturalidade") else ""
    estado_civil_txt = _bloco_estado_civil(pessoa_enriquecida)
    certidao_txt = ""  # certidao ja' embutida dentro de estado_civil_txt agora
    nome_fmt = _nome_negrito_maiusculo(pessoa_enriquecida)

    # Igual _incluir_regime_bens: quando o conjuge participante tem o
    # MESMO endereco do titular, a clausula de endereco tambem sai da
    # qualificacao INDIVIDUAL e vai uma unica vez, no final da frase
    # fundida (ver _fundir_qualificacao_conjugal) -- em vez de repetir
    # "residente e domiciliado em X" duas vezes com o mesmo endereco.
    incluir_endereco = pessoa_enriquecida.get("_incluir_endereco", True)
    endereco_txt = (
        f"{pessoa_enriquecida.get('residente_domiciliado_a', 'residente e domiciliado(a)')} em {campo('endereco')}"
        if incluir_endereco else ""
    )

    if (pessoa_enriquecida.get("tipo_documento_identidade") or "").strip().upper() == "CNH":
        # Caso 1: a pessoa so' tem UM documento de identidade, e por
        # acaso e' uma CNH (que ja' traz o RG impresso dentro dela) --
        # redacao propria, ditada pelo usuario: cita a CNH primeiro,
        # 'onde consta' a Cedula de Identidade.
        orgao_cnh_txt = f"/{campo('orgao_cnh')}" if pessoa_enriquecida.get("orgao_cnh") else ""
        orgao_rg_txt = f"/{campo('orgao_expedidor')}" if pessoa_enriquecida.get("orgao_expedidor") else ""
        texto_base = (
            f"{nome_fmt}, {campo('nacionalidade')}{natural_txt}, maior e capaz{estado_civil_txt}"
            f", {campo('profissao')}, "
            f"{pessoa_enriquecida.get('portador_a', 'portador(a)')} da Carteira Nacional de Habilitação "
            f"nº {campo('numero_cnh')}{orgao_cnh_txt}, expedida em {campo('data_expedicao_cnh')}, "
            f"onde consta a Cédula de Identidade nº {campo('rg')}{orgao_rg_txt}, "
            f"{pessoa_enriquecida.get('inscrito_a', 'inscrito(a)')} no CPF/MF sob nº {campo('cpf')}, "
            f"{certidao_txt}"
            f"{endereco_txt}"
        )
    elif pessoa_enriquecida.get("cnh_numero"):
        # Caso 2: RG e CNH foram enviados como documentos SEPARADOS (dois
        # uploads distintos) -- cada um citado com seu proprio "portador",
        # igual os exemplos reais que o usuario mandou (os dois documentos
        # aparecem lado a lado, nenhum "dentro" do outro).
        orgao_rg_txt = f"/{campo('orgao_expedidor')}" if pessoa_enriquecida.get("orgao_expedidor") else ""
        orgao_cnh_txt = f"/{campo('cnh_orgao_emissor')}" if pessoa_enriquecida.get("cnh_orgao_emissor") else ""
        portador_a = pessoa_enriquecida.get('portador_a', 'portador(a)')
        texto_base = (
            f"{nome_fmt}, {campo('nacionalidade')}{natural_txt}, maior e capaz{estado_civil_txt}"
            f", {campo('profissao')}, "
            f"{portador_a} da Cédula de Identidade nº {campo('rg')}{orgao_rg_txt}, "
            f"{portador_a} da Carteira Nacional de Habilitação nº {campo('cnh_numero')}{orgao_cnh_txt}, "
            f"expedida em {campo('cnh_data_expedicao')}, "
            f"{pessoa_enriquecida.get('inscrito_a', 'inscrito(a)')} no CPF/MF sob nº {campo('cpf')}, "
            f"{certidao_txt}"
            f"{endereco_txt}"
        )
    else:
        orgao_txt = f"/{campo('orgao_expedidor')}" if pessoa_enriquecida.get("orgao_expedidor") else ""
        texto_base = (
            f"{nome_fmt}, {campo('nacionalidade')}{natural_txt}, maior e capaz{estado_civil_txt}"
            f", {campo('profissao')}, "
            f"{pessoa_enriquecida.get('portador_a', 'portador(a)')} da Cédula de Identidade nº {campo('rg')}{orgao_txt}, "
            f"{pessoa_enriquecida.get('inscrito_a', 'inscrito(a)')} no CPF/MF sob nº {campo('cpf')}, "
            f"{certidao_txt}"
            f"{endereco_txt}"
        )

    # Se o endereco foi omitido (fundido com o do conjuge, citado uma so'
    # vez no final -- ver acima), sobra uma virgula solta no fim de
    # texto_base (a frase do CPF sempre termina em ", " esperando a
    # clausula de endereco na sequencia). Remove essa pontuacao solta.
    texto_base = re.sub(r",\s*$", "", texto_base)

    return _envolver_com_procuracao(texto_base, pessoa_enriquecida)


def _fundir_qualificacao_conjugal(
    texto_titular: str, conjuge_enriquecido: dict, pessoa_enriquecida: dict, participacao: str,
    endereco_comum: str | None = None,
) -> str:
    """Junta a qualificacao do titular com a do conjuge PARTICIPANTE do
    ato (vende tambem, ou anui) numa frase so', terminando numa UNICA
    clausula de casamento/regime que cobre os dois -- em vez de cada
    qualificacao individual repetir 'casado(a) com fulano(a), sob o
    regime de...' (o bug original que motivou essa funcao: 'casado(a)'
    citado duas vezes, uma por pessoa, com o mesmo dado duplicado).

    'endereco_comum' funciona igual: quando os dois moram no mesmo
    lugar, o chamador (enriquecer_pessoa_com_concordancia) ja' suprimiu
    o endereco de CADA qualificacao individual, e aqui ele e' citado uma
    unica vez, junto da clausula de casamento.

    Pressupoe que tanto 'pessoa_enriquecida' quanto 'conjuge_enriquecido'
    ja' passaram por enriquecer_pessoa_com_concordancia com
    incluir_regime_bens=False (ou seja, o texto_qualificacao de cada um
    ja' vem SEM a clausula de regime embutida)."""
    texto_conjuge = conjuge_enriquecido["texto_qualificacao"]
    genero_conjuge = inferir_genero(conjuge_enriquecido)
    conector = "e seu marido" if genero_conjuge == "m" else "e sua mulher"

    estado_civil = (pessoa_enriquecida.get("estado_civil") or "casado").strip().lower()
    plural_estado_civil = "casados" if estado_civil.startswith("casad") else estado_civil
    regime = pessoa_enriquecida.get("regime_bens") or "[FALTA: regime_bens]"
    data_casamento = pessoa_enriquecida.get("data_casamento")
    numero_cert = pessoa_enriquecida.get("numero_certidao_estado_civil")
    data_emissao_cert = pessoa_enriquecida.get("data_emissao_certidao_estado_civil")
    cartorio_cert = pessoa_enriquecida.get("cartorio_certidao_estado_civil")

    clausula_endereco = f", ambos residentes e domiciliados em {endereco_comum}" if endereco_comum else ""
    clausula_final = f"{clausula_endereco}, ambos {plural_estado_civil} entre si, sob o regime de {regime}"
    if data_casamento:
        clausula_final += f", aos {data_casamento}"
    if numero_cert:
        clausula_final += (
            f", conforme certidão de casamento matriculada sob nº {numero_cert}, "
            f"emitida em {data_emissao_cert or '[FALTA: data_emissao_certidao_estado_civil]'}, "
            f"pelo {cartorio_cert or '[FALTA: cartorio_certidao_estado_civil]'}"
        )

    rotulo_anuencia = ", este último como anuente" if participacao == "anui" else ""

    return f"{texto_titular}; {conector} {texto_conjuge}{rotulo_anuencia}{clausula_final}"


def _envolver_com_procuracao(texto_base: str, pessoa_enriquecida: dict) -> str:
    """Se a pessoa for representada por procurador, acrescenta a
    qualificacao completa do procurador + os dados do proprio instrumento
    de procuracao, na redacao fornecida pelo usuario. As folhas/livro de
    ARQUIVAMENTO nesta Serventia (diferente das folhas/livro do
    Tabelionato ONDE FOI LAVRADA, que vem da extracao) ficam como
    [FALTA] de proposito -- sao preenchidas na hora da lavratura, igual
    ordem_lavratura/data_lavratura."""
    if not pessoa_enriquecida.get("representado_por_procurador"):
        return texto_base

    procurador = pessoa_enriquecida.get("procurador") or {}
    texto_procurador = procurador.get("texto_qualificacao") or "[FALTA: procurador]"
    genero = inferir_genero(pessoa_enriquecida)
    representado_a = "representado" if genero == "m" else "representada"

    info = pessoa_enriquecida.get("procuracao_info") or {}
    def campo_proc(chave):
        return info.get(chave) or f"[FALTA: procuracao.{chave}]"

    return (
        f"{texto_base}, neste ato {representado_a} por seu procurador: {texto_procurador}, "
        f"nos termos da Procuração Pública lavrada pelo {campo_proc('numero_tabeliao')}º Tabelião de "
        f"Notas de {campo_proc('comarca_tabeliao')}, às fls. {campo_proc('folhas')}, do livro "
        f"{campo_proc('livro')}, em data de {campo_proc('data_lavratura_procuracao')}, a qual fica "
        f"arquivada nestas notas, às folhas [FALTA: fls_arquivo_procuracao], do livro "
        f"[FALTA: livro_arquivo_procuracao]-R"
    )


def calcular_concordancia_grupo(pessoas: list) -> dict:
    """Dado a lista de pessoas de um lado (outorgantes OU outorgados),
    calcula {'numero': 'sing'|'plur', 'genero': 'm'|'f'} pra esse grupo.

    Regra pra genero em grupo com mais de uma pessoa: se TODAS forem do
    mesmo genero, usa esse genero; se for misto, usa masculino plural
    (convencao gramatical padrao em portugues -- decisao confirmada com
    o usuario)."""
    pessoas = [p for p in (pessoas or []) if p]
    if not pessoas:
        return {"numero": "sing", "genero": "m"}  # nunca deveria acontecer de verdade

    # '_peso_concordancia' conta como mais de 1 pessoa quando a entrada e'
    # uma qualificacao FUNDIDA de titular + conjuge participante (ver
    # enriquecer_pessoa_com_concordancia) -- sao 2 pessoas assinando,
    # mesmo sendo 1 entrada so' na lista de outorgantes/outorgados.
    total_pessoas = sum(p.get("_peso_concordancia", 1) for p in pessoas)
    numero = "sing" if total_pessoas <= 1 else "plur"

    generos = {inferir_genero(p) for p in pessoas}
    for p in pessoas:
        conjuge_enriquecido = p.get("conjuge_enriquecido")
        if conjuge_enriquecido:
            generos.add(inferir_genero(conjuge_enriquecido))
    genero = "f" if generos == {"f"} else "m"
    return {"numero": numero, "genero": genero}


def calcular_concordancia_quantidade(quantidade: int) -> dict:
    """Versao simplificada pra grupos de genero fixo (ex: grupo 4 --
    imovel) -- so' precisa saber singular ou plural, quantidade de itens."""
    return {"numero": "sing" if quantidade <= 1 else "plur"}


_PADRAO_TAG = re.compile(r"«([^:«»]+):(\d+)»")


def resolver_concordancia(texto: str, concordancia_por_grupo: dict) -> tuple[str, list[str]]:
    """Substitui toda tag «palavra:grupo» no texto pela forma resolvida,
    usando concordancia_por_grupo (dict: numero_do_grupo (int) ->
    {'numero': 'sing'|'plur', 'genero': 'm'|'f' (opcional, so' precisa
    se a palavra for do tipo pessoa)}).

    Retorna (texto_resolvido, avisos) -- avisos lista qualquer palavra
    tagueada que nao esteja cadastrada em nenhuma das duas tabelas (isso
    e' importante: significa que uma palavra nova apareceu no template e
    precisa ser cadastrada manualmente, em vez de arriscar um palpite
    errado numa escritura de verdade)."""
    avisos = []

    def resolver(match):
        palavra, grupo_str = match.group(1), match.group(2)
        grupo = int(grupo_str)
        conc = concordancia_por_grupo.get(grupo, {"numero": "sing", "genero": "m"})
        numero = conc.get("numero", "sing")

        if palavra in PALAVRAS_PESSOA:
            genero = conc.get("genero", "m")
            chave = ("m" if genero == "m" else "f") + ("s" if numero == "sing" else "p")
            return PALAVRAS_PESSOA[palavra][chave]

        if palavra in PALAVRAS_NUMERO_FIXO:
            chave = "s" if numero == "sing" else "p"
            return PALAVRAS_NUMERO_FIXO[palavra][chave]

        avisos.append(
            f"Palavra de concordância desconhecida: «{palavra}:{grupo}» -- não cadastrada em "
            f"concordancia.py, mantida como está no texto (provável erro de digitação ou palavra nova)."
        )
        return match.group(0)  # mantem a tag original visivel, pra ficar obvio que faltou cadastrar

    texto_resolvido = _PADRAO_TAG.sub(resolver, texto)
    return texto_resolvido, avisos
