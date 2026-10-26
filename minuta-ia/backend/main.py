"""
API do Copiloto Notarial -- expoe o motor Python ja construido e testado
(auth, extracao, validadores, motor de minuta) por HTTP, pro mockup
visual (mesmo arquivo pixel-perfeito que ja desenhamos) consumir de
verdade, em vez de mostrar dado fixo de mentira.

RODAR:
    uvicorn backend.main:app --reload --port 8000

Depois abre http://localhost:8000 no navegador -- essa API tambem serve
o mockup direto, entao nao precisa de servidor separado pro front.
"""
import os
import sys
import tempfile
import secrets
import re
from datetime import datetime, timezone, date
from concurrent.futures import ThreadPoolExecutor, as_completed

from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, Form, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from auth import verificar_login, criar_usuario, listar_usuarios, remover_usuario
from extrair_dados import extrair as _extrair_real, verificar_consolidacao_pj, TIPOS_CERTIDAO, escolher_condicao_dispensa_certidao, MODELO_POR_TIPO_CERTIDAO
from validadores import validar_cpf, validar_cnpj, valor_por_extenso
from consistencia import checar_divergencia_pessoa
from concordancia import inferir_genero
from historico import salvar_parte, buscar_por_documento
from perfil import carregar_perfil, salvar_perfil
from extracao_log import listar_extracoes_recentes, tempo_medio_por_tipo
from atividade import registrar_minuta, contar_minutas_mes, contar_minutas_total, listar_atividade_recente
from motor_minuta import (
    listar_modelos_disponiveis, obter_modelo,
    criar_modelo, salvar_item, remover_item, salvar_ordem,
)

# Modo de teste: com MODO_TESTE_SEM_IA=1 no ambiente, a API devolve dado
# fixo em vez de chamar a IA de verdade -- util pra testar o fluxo inteiro
# (upload, tela de confirmacao, geracao de minuta) sem gastar nenhuma
# chamada de API real. NUNCA fica ligado sem querer: precisa da variavel
# de ambiente explicita.
_MODO_TESTE = os.environ.get("MODO_TESTE_SEM_IA") == "1"

_DADOS_FAKE = {
    "pessoa": {
        "nome": "José Maria da Silva (DADO DE TESTE)", "estado_civil": "Casado",
        "cpf": "111.444.777-35", "rg": "12.345.678-9", "orgao_expedidor": "SSP/SP",
        "profissao": "Engenheiro", "endereco": "Rua Teste, 123", "nacionalidade": "brasileiro",
    },
    "pessoa_juridica": {
        "razao_social": "Empresa Teste LTDA (DADO DE TESTE)", "cnpj": "11.222.333/0001-81",
        "endereco_sede": "Av. Teste, 999", "nome_representante_legal": "Carlos Souza",
        "poderes_representante": "Administrador", "eh_consolidado": "sim",
        "data_do_documento": "22/06/2025",
    },
    "certidao_simplificada": {
        "razao_social": "Empresa Teste LTDA (DADO DE TESTE)", "cnpj": "11.222.333/0001-81",
        "ultimo_arquivamento_data": "22/06/2025", "ultimo_arquivamento_ato": "consolidação",
    },
    "imovel": {
        "descricao": "Apartamento nº 32 (DADO DE TESTE)", "endereco": "Rua das Palmeiras, 250",
        "matricula": "45.678", "oficio_registro": "1º Ofício", "comarca": "Catanduva/SP",
        "circunscricao": "1ª", "area": "85,40 m²", "proprietario_atual": "José Maria da Silva",
        "onus_vigente": "nenhum",
    },
}


def extrair(caminho_arquivo: str, tipo: str, modelo: str | None = None, contexto_extra: str | None = None, permitir_pular_paginas_sem_texto: bool = False) -> dict:
    # LEMBRETE (ja' custou bug 2x): esse wrapper de teste precisa ter
    # SEMPRE a mesma assinatura da funcao real em extrair_dados.py.
    # Toda vez que mudar os parametros de uma, mudar a outra tambem.
    if _MODO_TESTE:
        return dict(_DADOS_FAKE.get(tipo, {}))
    return _extrair_real(caminho_arquivo, tipo, modelo, contexto_extra=contexto_extra, permitir_pular_paginas_sem_texto=permitir_pular_paginas_sem_texto)


USUARIO_TESTE = "ewandro.teste"
SENHA_TESTE = "teste12345"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed automatico: se o banco estiver vazio (ex: resetou sozinho no
    # plano gratuito de hospedagem, que nao garante disco permanente),
    # recria um usuario de teste na hora, sem precisar rodar comando
    # nenhum -- assim sempre existe um login pronto pra usar.
    if not listar_usuarios():
        criar_usuario(USUARIO_TESTE, SENHA_TESTE, "Ewandro", "8º Tabelionato de Notas de Curitiba/PR", is_admin=True)
    yield


app = FastAPI(title="Copiloto Notarial API", lifespan=lifespan)

# CORS liberado pra qualquer origem -- simplifica teste local. Quando for
# pra producao de verdade, vale restringir pro dominio real do frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sessoes em memoria (token -> dados do usuario). Simples de proposito --
# nao e' JWT nem banco de sessao, mas resolve o problema real: antes,
# NENHUMA rota da API exigia login pra funcionar (so' a TELA pedia senha,
# o "motor" por tras aceitava qualquer chamada). Agora, quem nao tiver um
# token valido (obtido fazendo login) nao consegue chamar nada sensivel.
#
# Limitacao conhecida: sessoes somem se o servidor reiniciar (mesma
# limitacao de disco efemero que ja afeta usuarios.db/historico.db no
# plano gratuito) -- nesse caso, so' precisa logar de novo.
SESSOES: dict[str, dict] = {}


def _gerar_token(usuario: dict) -> str:
    token = secrets.token_urlsafe(32)
    SESSOES[token] = usuario
    return token


def exigir_login(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado. Faça login novamente.")
    token = authorization.removeprefix("Bearer ").strip()
    usuario = SESSOES.get(token)
    if not usuario:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada. Faça login novamente.")
    return usuario


# ---------------------------------------------------------------------------
# AUTENTICACAO
# ---------------------------------------------------------------------------
@app.post("/api/login")
def login(username: str = Form(...), senha: str = Form(...)):
    usuario = verificar_login(username, senha)
    if usuario:
        token = _gerar_token(usuario)
        return {"sucesso": True, "usuario": usuario, "token": token}
    raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")


@app.post("/api/logout")
def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        SESSOES.pop(authorization.removeprefix("Bearer ").strip(), None)
    return {"sucesso": True}


@app.get("/api/usuarios")
def listar_usuarios_endpoint(usuario: dict = Depends(exigir_login)):
    """Lista os logins cadastrados -- alimenta a tabela real da tela
    Configurações > Usuários, que antes mostrava so' um exemplo fixo
    ('João Silva') copiado do mockup visual e nunca conectado a dado
    de verdade."""
    return {
        "sou_admin": bool(usuario.get("is_admin")),
        "usuarios": [
            {
                "username": u[0], "nome_completo": u[1], "cartorio": u[2],
                "criado_em": u[3], "is_admin": bool(u[4]),
            }
            for u in listar_usuarios()
        ]
    }


@app.delete("/api/usuarios/{username}")
def remover_usuario_endpoint(username: str, usuario: dict = Depends(exigir_login)):
    if not usuario.get("is_admin"):
        raise HTTPException(status_code=403, detail="Só um administrador pode remover usuários.")
    if username == usuario.get("username"):
        raise HTTPException(status_code=400, detail="Não é possível remover o próprio usuário logado.")
    if not remover_usuario(username):
        raise HTTPException(status_code=404, detail=f"Usuário '{username}' não encontrado.")
    return {"sucesso": True}


@app.post("/api/usuarios")
def criar_usuario_endpoint(
    usuario: dict = Depends(exigir_login),
    nome: str = Form(""),
    cartorio: str = Form(""),
    username: str = Form(...),
    senha: str = Form(...),
):
    """Cria um novo login -- SÓ um administrador pode chamar isso (ver
    checagem abaixo). Substitui o antigo autocadastro público
    ('/api/criar-conta', mantido só por compatibilidade mas agora também
    travado): antes qualquer pessoa com o link do site podia criar a
    própria conta sozinha, o que nunca foi a intenção real do sistema
    (ver docstring de auth.py) -- só ficou exposto assim por causa do
    fluxo de 'Primeiro acesso? Criar conta' documentado no DEPLOY.md."""
    if not usuario.get("is_admin"):
        raise HTTPException(status_code=403, detail="Só um administrador pode cadastrar novos usuários.")
    if not username or not senha:
        raise HTTPException(status_code=400, detail="Preencha usuário e senha.")
    if criar_usuario(username, senha, nome, cartorio, is_admin=False):
        return {"sucesso": True}
    raise HTTPException(status_code=409, detail="Esse nome de usuário já existe.")


@app.post("/api/criar-conta")
def criar_conta(
    nome: str = Form(""),
    cartorio: str = Form(""),
    username: str = Form(...),
    senha: str = Form(...),
):
    """MANTIDO SÓ PRA NÃO QUEBRAR links antigos que apontem pra ele, mas
    agora sempre recusa -- o autocadastro público foi desligado de
    propósito (ver /api/usuarios acima, que é o caminho novo, admin-only).
    Se isso ainda for chamado de algum lugar do frontend, é sinal de que
    sobrou uma tela antiga de autocadastro que precisa ser removida."""
    raise HTTPException(
        status_code=403,
        detail="Autocadastro público desativado. Peça a um administrador do sistema para criar seu login.",
    )


# ---------------------------------------------------------------------------
# EXTRACAO DE DOCUMENTOS
# ---------------------------------------------------------------------------
def _salvar_upload_temp(arquivo: UploadFile) -> str:
    sufixo = "." + arquivo.filename.split(".")[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
        tmp.write(arquivo.file.read())
        return tmp.name


def _extrair_e_limpar(caminho: str, tipo: str, contexto_extra: str | None = None):
    """Roda a extracao e SEMPRE apaga o arquivo temporario depois, mesmo
    se der erro no meio -- sem isso, cada documento enviado (RG, contrato
    social, matricula) ficava acumulando pra sempre em disco, nunca era
    apagado. Em uso continuo isso enche o disco (principalmente grave num
    servidor com disco limitado, tipo o plano gratuito de hospedagem)."""
    try:
        return extrair(caminho, tipo, contexto_extra=contexto_extra)
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass  # arquivo pode ja ter sido removido, nao e' motivo pra quebrar a resposta


@app.post("/api/extrair")
def extrair_endpoint(tipo: str = Form(...), arquivo: UploadFile = None, usuario: dict = Depends(exigir_login)):
    if arquivo is None:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    try:
        caminho = _salvar_upload_temp(arquivo)
        dados = _extrair_e_limpar(caminho, tipo)
        return {"sucesso": True, "dados": dados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair: {e}")


@app.post("/api/validar-documento")
def validar_documento(tipo: str = Form(...), numero: str = Form(...), usuario: dict = Depends(exigir_login)):
    """Validacao de digito verificador -- sem IA, resposta instantanea."""
    if tipo == "cpf":
        return {"valido": validar_cpf(numero)}
    if tipo == "cnpj":
        return {"valido": validar_cnpj(numero)}
    raise HTTPException(status_code=400, detail="tipo deve ser 'cpf' ou 'cnpj'.")


def _extrair_com_erro_claro(caminho: str, tipo: str, rotulo_documento: str, contexto_extra: str | None = None):
    """Wrapper fino em volta de _extrair_e_limpar que transforma TimeoutError
    e outras excecoes em HTTPException com mensagem identificando qual
    documento especifico falhou -- usado em todo lugar que le documento
    (pessoa, empresa, certidao, matricula) pra nunca devolver erro 500 mudo."""
    try:
        return _extrair_e_limpar(caminho, tipo, contexto_extra=contexto_extra)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Ao ler {rotulo_documento}: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler {rotulo_documento}: {e}")


def _extrair_sem_apagar(caminho: str, tipo: str, rotulo_documento: str, contexto_extra: str | None = None, modelo: str | None = None, permitir_pular_paginas_sem_texto: bool = False):
    """Igual a _extrair_com_erro_claro, mas NAO apaga o arquivo temporario
    depois -- usado quando o MESMO arquivo (um "documento combinado")
    precisa ser lido varias vezes, uma por schema diferente (pessoa,
    certidao de estado civil, comprovante, ate' 7 certidoes negativas).
    Quem chama isso e' responsavel por apagar o arquivo no final, depois
    da ULTIMA leitura -- ver uso em _extrair_parte_completa_api.

    'modelo', quando passado, forca um modelo especifico pra ESSA chamada
    (ver MODELO_POR_TIPO_CERTIDAO em extrair_dados.py) -- usado pelas
    certidoes de tributos, que migraram pro Haiku.

    'permitir_pular_paginas_sem_texto', quando True, permite ao modo texto
    (ver extrair_dados.py) pular paginas de imagem/foto dentro do PDF
    combinado em vez de reprovar o documento inteiro -- SO' seguro pro
    fluxo de PESSOA (a pagina fraca e' sempre RG/CNH, nunca a certidao
    procurada). NUNCA passar True pra buscas dentro do PDF combinado do
    IMOVEL -- a certidao municipal la' pode ELA MESMA ser a pagina de
    imagem, e pular ela e' o bug que ja aconteceu uma vez (ver comentario
    extenso em extrair_dados.py)."""
    try:
        return extrair(caminho, tipo, modelo=modelo, contexto_extra=contexto_extra, permitir_pular_paginas_sem_texto=permitir_pular_paginas_sem_texto)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Ao ler {rotulo_documento}: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler {rotulo_documento}: {e}")


# Pool COMPARTILHADO pra todas as chamadas de extracao em paralelo dentro
# de um "documento combinado" (PDF unico). Cada chamada de IA e' uma
# espera de rede (I/O), entao threads resolvem bem aqui mesmo com o GIL
# do Python -- o tempo todo fica esperando resposta da API, nao
# calculando nada pesado localmente.
#
# max_workers deliberadamente baixo (6): alto o suficiente pra tirar a
# maior parte do ganho de paralelizar ~11 chamadas de um PDF unico de
# pessoa, mas baixo o suficiente pra nao estourar rate limit da API
# quando varias pessoas/imovel do MESMO caso rodam em sequencia (cada
# uma usando ate' 6 conexoes simultaneas por vez, nunca todas de uma vez
# o caso inteiro).
_EXECUTOR_EXTRACAO_PARALELA = ThreadPoolExecutor(max_workers=6)


def _extrair_varios_em_paralelo(tarefas: dict) -> dict:
    """Roda varias chamadas de extracao (mesma logica de _extrair_sem_apagar,
    ou seja: NUNCA apaga arquivo) ao mesmo tempo, usando o pool
    compartilhado acima.

    'tarefas' e' um dict {chave: (caminho, tipo, rotulo)} ou {chave:
    (caminho, tipo, rotulo, contexto_extra)} -- o 4o item e' opcional,
    usado quando o MESMO arquivo esta' sendo lido varias vezes pra tipos
    diferentes de certidao (ver _extrair_certidoes_pessoa_combinado),
    onde cada chamada precisa dizer pra IA qual certidao especifica
    procurar dentre varias presentes no arquivo. Devolve um dict
    {chave: resultado} onde 'resultado' e' o dict extraido em caso de
    sucesso, ou a EXCECAO (HTTPException) em caso de falha -- quem chama
    decide se aquela chave especifica e' obrigatoria (propaga o erro) ou
    uma tentativa opcional (trata como '{}' se vier excecao).

    Nunca lanca excecao sozinha -- devolver a excecao como valor, em vez
    de deixar ela subir e cancelar as OUTRAS tarefas que ainda estao
    rodando, e' proposital: um documento ilegivel dentro do combinado nao
    deve derrubar a extracao dos outros 6 que estavam indo bem."""
    resultados = {}
    with_futuros = {
        _EXECUTOR_EXTRACAO_PARALELA.submit(_extrair_sem_apagar, *args): chave
        for chave, args in tarefas.items()
    }
    for futuro in as_completed(with_futuros):
        chave = with_futuros[futuro]
        try:
            resultados[chave] = futuro.result()
        except Exception as e:
            resultados[chave] = e
    return resultados


def _extrair_parte_api(tipo_pessoa: str, doc=None, contrato=None, representante=None, simplificada=None, rotulo: str = ""):
    """Mesma logica do extrair_parte() do app.py Streamlit, reescrita aqui
    pra API -- extrai PF (um documento) ou PJ (contrato + representante,
    e opcionalmente certidao simplificada pra checar consolidacao)."""
    alertas = []
    if tipo_pessoa == "PF":
        if doc is None or not getattr(doc, "filename", None):
            raise HTTPException(status_code=400, detail=f"Documento de identificação do {rotulo} não enviado.")
        caminho = _salvar_upload_temp(doc)
        dados = _extrair_com_erro_claro(caminho, "pessoa", f"documento de identificação do {rotulo}")
        dados["_tipo"] = "PF"
        if dados.get("cpf") and not validar_cpf(dados["cpf"]):
            alertas.append(f"{rotulo}: CPF '{dados['cpf']}' tem dígito verificador inválido — provável erro de leitura, confira o documento original.")
        return dados, alertas

    if contrato is None or representante is None or not getattr(contrato, "filename", None) or not getattr(representante, "filename", None):
        raise HTTPException(status_code=400, detail=f"Contrato Social e documento do representante do {rotulo} são obrigatórios para Pessoa Jurídica.")
    caminho_contrato = _salvar_upload_temp(contrato)
    dados = _extrair_com_erro_claro(caminho_contrato, "pessoa_juridica", f"contrato social do {rotulo}")
    dados["_tipo"] = "PJ"

    if dados.get("cnpj") and not validar_cnpj(dados["cnpj"]):
        alertas.append(f"{rotulo}: CNPJ '{dados['cnpj']}' tem dígito verificador inválido — provável erro de leitura, confira o documento original.")

    dados_simplificada = None
    if simplificada is not None and getattr(simplificada, "filename", None):
        caminho_simpl = _salvar_upload_temp(simplificada)
        dados_simplificada = _extrair_com_erro_claro(caminho_simpl, "certidao_simplificada", f"certidão simplificada do {rotulo}")
    alertas.extend(f"{rotulo}: {a}" for a in verificar_consolidacao_pj(dados, dados_simplificada))

    # nire so' vem da Certidao Simplificada (o Contrato Social normalmente
    # nao traz esse numero) -- antes ficava so' dentro de dados_simplificada,
    # usado so' pra checar divergencia, e nunca chegava no dado final da PJ
    # (por isso a qualificacao nunca conseguia citar o NIRE).
    if dados_simplificada and dados_simplificada.get("nire"):
        dados["nire"] = dados_simplificada["nire"]
    if dados_simplificada and dados_simplificada.get("data_emissao"):
        dados["data_certidao_simplificada"] = dados_simplificada["data_emissao"]

    caminho_rep = _salvar_upload_temp(representante)
    dados["representante"] = _extrair_com_erro_claro(caminho_rep, "pessoa", f"documento do representante do {rotulo}")

    return dados, alertas


def _contexto_busca_certidao_especifica(nome_legivel: str) -> str:
    """Instrucao ADICIONAL (fora da parte fixa/cacheada do prompt) pra
    quando o schema generico 'certidao' e' chamado varias vezes contra o
    MESMO arquivo combinado -- sem isso, a IA nao tinha como saber QUAL
    das varias certidoes presentes no arquivo ela deveria achar em cada
    chamada especifica, e podia devolver o resultado errado (ou vazio)
    mesmo com o documento certo la' dentro. Bug real encontrado: um PDF
    combinado com 5+ certidoes diferentes (trabalhista, TRT, TRF,
    estadual, federal) fazia varias delas saírem como "nao encontrada"
    mesmo estando visivelmente presentes no arquivo."""
    return f"""IMPORTANTE -- ESTE ARQUIVO PODE SER UM PDF COMBINADO:
O documento anexado pode conter VARIOS documentos diferentes juntos no
mesmo arquivo (RG, CNH, certidao de casamento, comprovante de
residencia, e ate' 7 certidoes negativas de tipos diferentes).

Sua tarefa NESTA chamada e' especificamente encontrar e extrair a:
{nome_legivel}

Ignore COMPLETAMENTE qualquer outro documento ou certidao presente no
arquivo que NAO seja exatamente esse tipo -- mesmo que pareca uma
certidao valida, se nao for do tipo pedido aqui, nao a utilize.

Se esse tipo especifico de certidao nao estiver presente em NENHUMA
pagina do arquivo, retorne todos os campos como null. Nao misture dados
de uma certidao diferente por engano so' porque ela tambem esta' no
arquivo."""


def _extrair_certidoes_pessoa_combinado(caminho_combinado: str, rotulo: str):
    """Mesma ideia de _extrair_certidoes_pessoa, mas tentando achar as 7
    certidoes fixas dentro do MESMO arquivo combinado, em vez de um
    upload por tipo -- so' aceita o resultado de cada tentativa se
    realmente veio numero OU situacao (a IA pode simplesmente nao achar
    aquela certidao especifica dentro do documento, porque genuinamente
    nao esta' la', e nesse caso devolve campos vazios em vez de dar erro
    -- nao finge que achou so' porque a chamada nao falhou).

    As 7 tentativas rodam em PARALELO (mesmo arquivo, schemas diferentes)
    -- e' o principal gargalo de tempo do PDF unico, e nenhuma delas
    depende do resultado de outra, entao esperar uma terminar pra so' ai'
    comecar a proxima era desperdicio puro de tempo.

    IMPORTANTE (cache do documento): como todas as 7 leem o MESMO arquivo
    com cache_control ligado (ver extrair_dados.py), rodar as 7 TODAS ao
    mesmo tempo faria a maioria "disputar" um cache ainda vazio (a
    escrita do cache so' fica pronta quando a chamada termina de
    processar) -- nenhuma delas se beneficiaria. Por isso a PRIMEIRA
    chamada roda sozinha, sincrona, pra "esquentar" o cache; so' DEPOIS
    dela terminar e' que as outras 6 disparam em paralelo e conseguem de
    fato reaproveitar o cache escrito pela primeira.

    IMPORTANTE (modelo por tipo): 2 dos 7 tipos (tributos federais e
    estaduais) rodam no Haiku em vez do Sonnet padrao -- ver
    MODELO_POR_TIPO_CERTIDAO em extrair_dados.py pra criterio e aviso de
    validacao antes de promover mais tipos pra essa lista."""
    certidoes = {}
    condicoes = {}
    tarefas = {
        tipo_id: (
            caminho_combinado, "certidao", f"{nome_legivel} do {rotulo} (documento combinado)",
            _contexto_busca_certidao_especifica(nome_legivel),
            MODELO_POR_TIPO_CERTIDAO.get(tipo_id),  # None = usa o padrao (Sonnet) da funcao extrair()
            True,  # permitir_pular_paginas_sem_texto -- seguro aqui: a unica pagina fraca possivel
                   # no combinado de PESSOA e' RG/CNH, que nunca e' a certidao procurada.
                   # NUNCA copiar esse True pra uma busca dentro do combinado do IMOVEL.
        )
        for tipo_id, nome_legivel in TIPOS_CERTIDAO
    }

    primeira_chave, primeira_tarefa = next(iter(tarefas.items()))
    try:
        resultados = {primeira_chave: _extrair_sem_apagar(*primeira_tarefa)}
    except Exception as e:
        resultados = {primeira_chave: e}
    tarefas_restantes = {k: v for k, v in tarefas.items() if k != primeira_chave}
    resultados.update(_extrair_varios_em_paralelo(tarefas_restantes))

    for tipo_id, _nome_legivel in TIPOS_CERTIDAO:
        condicao_dispensa = escolher_condicao_dispensa_certidao(tipo_id)
        resultado = resultados[tipo_id]
        extraido = {} if isinstance(resultado, Exception) else resultado
        if extraido.get("numero") or extraido.get("situacao"):
            certidoes[tipo_id] = extraido
            condicoes[condicao_dispensa] = False
        else:
            certidoes[tipo_id] = None
            condicoes[condicao_dispensa] = True

    # "feitos_comarca_diferente" nao se aplica ao modo combinado -- e' uma
    # lista repetivel pensada pra upload avulso, nao faz sentido tentar
    # "adivinhar" quantas comarcas diferentes existem dentro de um unico
    # arquivo combinado.
    certidoes["feitos_comarca_diferente"] = []
    condicoes["certidao_feitos_comarca_diferente_dispensada"] = True
    return certidoes, condicoes


def _extrair_certidoes_pessoa(form, prefixo: str, rotulo: str):
    """Extrai as certidoes de uma pessoa (outorgante/outorgado) a partir
    dos campos do form com o prefixo indicado (ex: 'outorgante_0').

    Retorna (certidoes: dict, condicoes: dict, avisos: list).

    'certidoes' tem uma chave por tipo fixo (dados extraidos, ou None se
    a certidao nao foi enviada) + a chave 'feitos_comarca_diferente' com
    uma LISTA -- esse e' o unico tipo sem slot fixo unico, pode ter zero,
    um ou mais arquivos (o botao '+ Adicionar comarca diferente' no
    front manda quantos precisar, cada um com a mesma chave repetida).

    'condicoes' ja vem pronto no formato que o motor de minuta espera:
    uma flag True por certidao que NAO foi enviada (dispensada) -- e'
    isso que faz cada clausula sumir individualmente no sub-item
    correspondente, em vez de tudo-ou-nada."""
    certidoes = {}
    condicoes = {}

    for tipo_id, nome_legivel in TIPOS_CERTIDAO:
        chave = f"{prefixo}_certidao_{tipo_id}"
        arquivo = form.get(chave)
        condicao_dispensa = escolher_condicao_dispensa_certidao(tipo_id)

        if arquivo is None or not getattr(arquivo, "filename", None):
            certidoes[tipo_id] = None
            condicoes[condicao_dispensa] = True
            continue

        caminho = _salvar_upload_temp(arquivo)
        certidoes[tipo_id] = _extrair_com_erro_claro(caminho, "certidao", f"{nome_legivel} do {rotulo}")
        condicoes[condicao_dispensa] = False

    chave_comarca = f"{prefixo}_certidao_feitos_comarca_diferente"
    arquivos_comarca = form.getlist(chave_comarca) if hasattr(form, "getlist") else []
    lista_comarca = []
    for arquivo in arquivos_comarca:
        if not getattr(arquivo, "filename", None):
            continue
        caminho = _salvar_upload_temp(arquivo)
        lista_comarca.append(
            _extrair_com_erro_claro(caminho, "certidao", f"certidão de comarca diferente do {rotulo}")
        )
    certidoes["feitos_comarca_diferente"] = lista_comarca
    condicoes["certidao_feitos_comarca_diferente_dispensada"] = (len(lista_comarca) == 0)

    return certidoes, condicoes


def _preferir_regime_bens_da_matricula(dados_pessoa: dict, dados_imovel: dict) -> str | None:
    """Se a matricula do imovel trouxer o regime de bens de forma mais
    ESPECIFICA do que a certidao de estado civil da propria pessoa (ex:
    certidao generica 'comunhao de bens', matricula especifica 'comunhao
    universal de bens'), atualiza dados_pessoa['regime_bens'] pra usar a
    versao mais especifica -- e devolve um aviso pra revisao manual (nunca
    faz essa troca silenciosamente numa escritura de verdade).

    So' entra em acao pra palavras de regime que a matricula deixa
    inequivocamente mais especificas (universal/parcial/separacao total)
    e que a certidao NAO ja' mencione -- nunca sobrescreve um regime que
    a propria certidao ja' deixou especifico."""
    regime_atual = (dados_pessoa.get("regime_bens") or "").strip().lower()
    if not regime_atual:
        return None  # sem regime nenhum pra comparar, nada a fazer aqui

    texto_matricula = (dados_imovel.get("proprietarios_atuais_estado_civil") or "").lower()
    if not texto_matricula:
        return None

    termos_especificos = ["universal", "parcial", "separação total", "separacao total", "participação final", "participacao final"]
    for termo in termos_especificos:
        if termo in texto_matricula and termo not in regime_atual:
            regime_original = dados_pessoa.get("regime_bens")
            regime_especifico = f"comunhão {termo} de bens" if termo in ("universal", "parcial") else termo
            dados_pessoa["regime_bens"] = regime_especifico
            return (
                f"regime de bens ajustado de '{regime_original}' (genérico, vindo da "
                f"certidão) para uma versão mais específica encontrada na matrícula do imóvel "
                f"('{termo}') — confira se está correto antes de lavrar."
            )
    return None


def _extrair_parte_completa_api(form, prefixo: str, rotulo: str):
    """Extrai uma parte (outorgante OU outorgado) por completo: dados
    pessoais (PF ou PJ) + certidao de estado civil (se enviada) + as
    certidoes de dispensa associadas a ela -- usando os campos do form
    com o prefixo indicado (ex: 'outorgante_0').

    Modo "PDF unico" ({prefixo}_combinado): quando presente (so' faz
    sentido pra PF), o MESMO arquivo e' usado pra tentar todas as
    extracoes (identidade, estado civil, comprovante, CNH, as 7
    certidoes negativas) em vez de exigir um upload por documento. Cada
    tentativa so' e' aceita se realmente achar dado -- o que nao for
    encontrado dentro do arquivo simplesmente fica pendente, do mesmo
    jeito que ficaria se o upload individual nunca tivesse sido feito."""
    tipo_pessoa = (form.get(f"{prefixo}_tipo") or "PF")
    if hasattr(tipo_pessoa, "strip"):
        tipo_pessoa = tipo_pessoa.strip() or "PF"

    combinado_doc = form.get(f"{prefixo}_combinado")
    usa_combinado = tipo_pessoa == "PF" and combinado_doc is not None and getattr(combinado_doc, "filename", None)

    caminho_combinado = None
    if usa_combinado:
        caminho_combinado = _salvar_upload_temp(combinado_doc)

        # As 4 tentativas (identidade + estado civil + comprovante + CNH)
        # leem o MESMO arquivo com schemas diferentes -- nenhuma depende
        # do resultado de outra, entao rodam todas de uma vez em vez de
        # esperar uma terminar pra so' ai' comecar a proxima (esse era o
        # principal gargalo de tempo do PDF unico: 4 chamadas sequenciais
        # de rede, uma atras da outra, quando podiam ser 1 so' "rodada").
        resultados_combinado = _extrair_varios_em_paralelo({
            "pessoa": (caminho_combinado, "pessoa", f"documento combinado do {rotulo}"),
            "estado_civil": (caminho_combinado, "certidao_estado_civil", f"documento combinado do {rotulo}"),
            "comprovante": (caminho_combinado, "comprovante_residencia", f"documento combinado do {rotulo}"),
            "cnh": (caminho_combinado, "cnh", f"documento combinado do {rotulo}"),
        })

        # A identidade ("pessoa") e' a UNICA obrigatoria das 4 -- sem ela
        # nao da' pra montar nada. Se ela falhou, propaga o erro de
        # verdade (com a mensagem especifica de qual documento/motivo).
        # As outras 3 sao "tentativas" opcionais -- erro nelas so' vira
        # dict vazio, exatamente como se aquele documento nunca tivesse
        # sido enviado.
        if isinstance(resultados_combinado["pessoa"], Exception):
            try:
                os.unlink(caminho_combinado)
            except OSError:
                pass
            raise resultados_combinado["pessoa"]

        dados = resultados_combinado["pessoa"]
        dados["_tipo"] = "PF"
        alertas = []
        if dados.get("cpf") and not validar_cpf(dados["cpf"]):
            alertas.append(f"{rotulo}: CPF '{dados['cpf']}' tem dígito verificador inválido — confira o documento original.")

        dados_ec = resultados_combinado["estado_civil"]
        if isinstance(dados_ec, Exception):
            dados_ec = {}
        tem_certidao_estado_civil = bool(dados_ec.get("tipo_documento"))

        dados_comp = resultados_combinado["comprovante"]
        if isinstance(dados_comp, Exception):
            dados_comp = {}

        dados_cnh = resultados_combinado["cnh"]
        if isinstance(dados_cnh, Exception):
            dados_cnh = {}
    else:
        doc = form.get(f"{prefixo}_doc")
        contrato = form.get(f"{prefixo}_contrato")
        representante = form.get(f"{prefixo}_representante")
        simplificada = form.get(f"{prefixo}_simplificada")
        dados, alertas = _extrair_parte_api(tipo_pessoa, doc, contrato, representante, simplificada, rotulo)

    # Certidao de estado civil (nascimento/casamento/casamento com
    # averbacao de divorcio) -- opcional, so' faz sentido pra PF. Quando
    # encontrada, ela e' a FONTE DE VERDADE do estado civil da pessoa --
    # nao o RG (que na maioria das vezes nem imprime estado civil, e
    # quando imprime pode estar desatualizado). Tambem mescla nome do
    # conjuge, regime de bens e detalhes de divorcio, que alimentam a
    # clausula de qualificacao com anuencia do conjuge.
    if not usa_combinado:
        estado_civil_doc = form.get(f"{prefixo}_estado_civil")
        tem_certidao_estado_civil = (
            tipo_pessoa == "PF" and estado_civil_doc is not None and getattr(estado_civil_doc, "filename", None)
        )
        dados_ec = {}
        if tem_certidao_estado_civil:
            caminho_ec = _salvar_upload_temp(estado_civil_doc)
            dados_ec = _extrair_com_erro_claro(caminho_ec, "certidao_estado_civil", f"certidão de estado civil do {rotulo}")

    if tipo_pessoa == "PF" and tem_certidao_estado_civil:
        dados["certidao_estado_civil"] = dados_ec

        # genero pela nacionalidade (RG quase sempre traz isso generizado
        # -- 'brasileiro'/'brasileira' -- muito mais confiavel que tentar
        # ler genero de qualquer outro campo). Reusa a mesma funcao
        # central de concordancia.py, que ja' tem a defesa contra a IA
        # devolver algo tipo 'brasileiro(a)' apesar da instrucao do schema.
        genero = inferir_genero(dados)

        tipo_doc_ec = (dados_ec.get("tipo_documento") or "").strip().lower()
        estado_civil_por_tipo = {
            "nascimento": {"m": "solteiro", "f": "solteira"},
            "casamento": {"m": "casado", "f": "casada"},
            "casamento_com_averbacao_divorcio": {"m": "divorciado", "f": "divorciada"},
            "casamento_com_averbacao_obito": {"m": "viúvo", "f": "viúva"},
            "casamento_com_averbacao_separacao": {"m": "separado", "f": "separada"},
        }
        if tipo_doc_ec in estado_civil_por_tipo:
            dados["estado_civil"] = estado_civil_por_tipo[tipo_doc_ec][genero]

        if dados_ec.get("nome_conjuge"):
            dados["nome_conjuge"] = dados_ec["nome_conjuge"]
        if dados_ec.get("regime_bens"):
            dados["regime_bens"] = dados_ec["regime_bens"]
        if dados_ec.get("data_casamento"):
            dados["data_casamento"] = dados_ec["data_casamento"]
        if dados_ec.get("numero_certidao"):
            dados["numero_certidao_estado_civil"] = dados_ec["numero_certidao"]
        if dados_ec.get("data_emissao"):
            dados["data_emissao_certidao_estado_civil"] = dados_ec["data_emissao"]
        if dados_ec.get("cartorio_emissor"):
            dados["cartorio_certidao_estado_civil"] = dados_ec["cartorio_emissor"]
        if dados_ec.get("tem_averbacao_divorcio"):
            dados["tem_averbacao_divorcio"] = dados_ec["tem_averbacao_divorcio"]
            dados["data_divorcio"] = dados_ec.get("data_divorcio")
        if dados_ec.get("tem_averbacao_obito"):
            dados["data_obito_conjuge"] = dados_ec.get("data_obito")
        if dados_ec.get("tem_averbacao_separacao"):
            dados["data_separacao"] = dados_ec.get("data_separacao")
        # averbacao fora do padrao (casamentos multiplos, interdicao,
        # etc.) -- nao tenta decidir nada sozinho, so' vira alerta pro
        # tabeliao conferir manualmente
        if dados_ec.get("outras_averbacoes_relevantes"):
            alertas.append(
                f"{rotulo}: certidão de estado civil traz algo fora do padrão — "
                f"{dados_ec['outras_averbacoes_relevantes']} Confira manualmente."
            )

    # Comprovante de residencia -- opcional, so' faz sentido pra PF.
    # Vira a FONTE DE VERDADE do endereco quando encontrado (RG raramente
    # traz endereco, e quando traz pode estar desatualizado).
    if not usa_combinado:
        dados_comp = {}
        comprovante_doc = form.get(f"{prefixo}_comprovante")
        if tipo_pessoa == "PF" and comprovante_doc is not None and getattr(comprovante_doc, "filename", None):
            caminho_comp = _salvar_upload_temp(comprovante_doc)
            dados_comp = _extrair_com_erro_claro(caminho_comp, "comprovante_residencia", f"comprovante de residência do {rotulo}")
    if dados_comp.get("endereco"):
        dados["endereco"] = dados_comp["endereco"]

    # CNH -- opcional, so' faz sentido pra PF. Nao substitui o RG, entra
    # JUNTO na qualificacao quando presente (varias minutas reais citam
    # os dois documentos ao mesmo tempo: "portador da Cedula de
    # Identidade... portador da CNH...").
    if not usa_combinado:
        dados_cnh = {}
        cnh_doc = form.get(f"{prefixo}_cnh")
        if tipo_pessoa == "PF" and cnh_doc is not None and getattr(cnh_doc, "filename", None):
            caminho_cnh = _salvar_upload_temp(cnh_doc)
            dados_cnh = _extrair_com_erro_claro(caminho_cnh, "cnh", f"CNH do {rotulo}")
    if dados_cnh.get("numero"):
        dados["cnh_numero"] = dados_cnh["numero"]
        dados["cnh_orgao_emissor"] = dados_cnh.get("orgao_emissor")
        dados["cnh_data_expedicao"] = dados_cnh.get("data_expedicao")

    # Procuracao -- opcional, so' quando o toggle "Por procuracao" estiver
    # ativo. Independente do modo combinado (o procurador sempre tem seu
    # proprio documento de procuracao, nunca faz parte do "PDF unico" do
    # outorgante/outorgado). O procurador NAO precisa de upload de RG
    # proprio -- a qualificacao completa dele normalmente ja' vem descrita
    # no proprio texto do instrumento de procuracao, entao extraimos os
    # dois (dados do ato + qualificacao do procurador) do mesmo documento.
    por_procuracao = (form.get(f"{prefixo}_por_procuracao") or "").strip().lower() == "true"
    procuracao_doc = form.get(f"{prefixo}_procuracao")
    if por_procuracao and procuracao_doc is not None and getattr(procuracao_doc, "filename", None):
        caminho_proc = _salvar_upload_temp(procuracao_doc)
        dados_proc = _extrair_com_erro_claro(caminho_proc, "procuracao", f"procuração do {rotulo}")
        dados["representado_por_procurador"] = True
        dados["procuracao_info"] = {
            "numero_tabeliao": dados_proc.get("numero_tabeliao"),
            "comarca_tabeliao": dados_proc.get("comarca_tabeliao"),
            "folhas": dados_proc.get("folhas"),
            "livro": dados_proc.get("livro"),
            "data_lavratura_procuracao": dados_proc.get("data_lavratura_procuracao"),
        }
        dados["procurador"] = {
            "nome": dados_proc.get("nome_procurador"),
            "nacionalidade": dados_proc.get("nacionalidade_procurador"),
            "sexo": dados_proc.get("sexo_procurador"),
            "estado_civil": dados_proc.get("estado_civil_procurador"),
            "profissao": dados_proc.get("profissao_procurador"),
            "rg": dados_proc.get("rg_procurador"),
            "orgao_expedidor": dados_proc.get("orgao_expedidor_procurador"),
            "cpf": dados_proc.get("cpf_procurador"),
            "endereco": dados_proc.get("endereco_procurador"),
        }

    # Participacao do conjuge no ato -- so' faz sentido pra PF casado(a).
    # 3 opcoes: 'so_qualifica' (default, comportamento antigo -- conjuge so'
    # e' citado na qualificacao, nao assina), 'outorga_tambem' (conjuge
    # tambem e' outorgante/outorgado -- vira co-vendedor/co-comprador, e por
    # isso precisa das MESMAS certidoes exigidas do titular) ou 'anui'
    # (conjuge consente com o ato mas nao e' parte -- nao precisa de
    # certidao propria, so' qualificacao). Quando 'outorga_tambem' ou
    # 'anui', o documento do conjuge e' extraido (schema 'pessoa', igual
    # qualquer PF) e a qualificacao fundida e' montada em concordancia.py.
    # Independente do modo combinado do titular -- o conjuge sempre tem
    # upload proprio, nunca entra dentro do "documento combinado".
    conjuge_participacao = (form.get(f"{prefixo}_conjuge_participacao") or "so_qualifica").strip().lower()
    if conjuge_participacao not in ("so_qualifica", "outorga_tambem", "anui"):
        conjuge_participacao = "so_qualifica"

    condicoes_cert_conjuge = {}
    conjuge_combinado_doc = form.get(f"{prefixo}_conjuge_combinado")
    usa_combinado_conjuge = (
        tipo_pessoa == "PF" and conjuge_participacao == "outorga_tambem"
        and conjuge_combinado_doc is not None and getattr(conjuge_combinado_doc, "filename", None)
    )

    if tipo_pessoa == "PF" and conjuge_participacao in ("outorga_tambem", "anui") and usa_combinado_conjuge:
        # PDF unico do CONJUGE -- so' identidade + as 7 certidoes do mesmo
        # arquivo. NUNCA tenta estado civil/comprovante aqui: esses dois ja'
        # vieram do lado do TITULAR (secao acima) e sao dados DO CASAL, nao
        # da pessoa individual -- ler de novo do documento do conjuge correria
        # o risco de a IA achar um endereco ou regime de bens ligeiramente
        # diferente e um lado sobrescrever o outro sem ninguem perceber.
        caminho_conjuge_combinado = _salvar_upload_temp(conjuge_combinado_doc)
        try:
            dados_conjuge = _extrair_sem_apagar(caminho_conjuge_combinado, "pessoa", f"documento combinado do cônjuge do {rotulo}")
        except HTTPException:
            try:
                os.unlink(caminho_conjuge_combinado)
            except OSError:
                pass
            raise
        dados_conjuge["_tipo"] = "PF"
        if dados_conjuge.get("cpf") and not validar_cpf(dados_conjuge["cpf"]):
            alertas.append(f"{rotulo}: CPF do cônjuge '{dados_conjuge['cpf']}' tem dígito verificador inválido — confira o documento original.")
        dados["conjuge_participante"] = {"participacao": conjuge_participacao, "dados": dados_conjuge}

        certidoes_conjuge, condicoes_cert_conjuge_brutas = _extrair_certidoes_pessoa_combinado(
            caminho_conjuge_combinado, f"cônjuge do {rotulo}"
        )
        dados_conjuge["certidoes"] = certidoes_conjuge
        condicoes_cert_conjuge = {f"conjuge_{k}": v for k, v in condicoes_cert_conjuge_brutas.items()}

        try:
            os.unlink(caminho_conjuge_combinado)
        except OSError:
            pass

    elif tipo_pessoa == "PF" and conjuge_participacao in ("outorga_tambem", "anui"):
        conjuge_doc = form.get(f"{prefixo}_conjuge_doc")
        if conjuge_doc is None or not getattr(conjuge_doc, "filename", None):
            alertas.append(
                f"{rotulo}: participação do cônjuge marcada como "
                f"'{'outorga também' if conjuge_participacao == 'outorga_tambem' else 'anui'}', "
                f"mas o documento de identificação do cônjuge não foi enviado — qualificação "
                f"fundida não pôde ser montada, mantido o comportamento simples de qualificação."
            )
        else:
            caminho_conjuge = _salvar_upload_temp(conjuge_doc)
            dados_conjuge = _extrair_com_erro_claro(caminho_conjuge, "pessoa", f"documento do cônjuge do {rotulo}")
            dados_conjuge["_tipo"] = "PF"
            if dados_conjuge.get("cpf") and not validar_cpf(dados_conjuge["cpf"]):
                alertas.append(f"{rotulo}: CPF do cônjuge '{dados_conjuge['cpf']}' tem dígito verificador inválido — confira o documento original.")
            dados["conjuge_participante"] = {"participacao": conjuge_participacao, "dados": dados_conjuge}

            # 'outorga_tambem' torna o conjuge um verdadeiro co-outorgante/
            # co-outorgado -- por isso precisa apresentar as mesmas
            # certidoes pessoais exigidas do titular (trabalhista, feitos
            # ajuizados, tributos etc.). 'anui' nao precisa: ele consente,
            # mas nao responde como parte no negocio.
            if conjuge_participacao == "outorga_tambem":
                certidoes_conjuge, condicoes_cert_conjuge_brutas = _extrair_certidoes_pessoa(
                    form, f"{prefixo}_conjuge", f"cônjuge do {rotulo}"
                )
                dados_conjuge["certidoes"] = certidoes_conjuge
                # prefixo proprio nas chaves de condicao pra nao colidir com
                # as do titular (ex: 'certidao_trabalhista_dispensada' do
                # titular vs. a mesma chave pro conjuge)
                condicoes_cert_conjuge = {f"conjuge_{k}": v for k, v in condicoes_cert_conjuge_brutas.items()}

    if usa_combinado:
        certidoes, condicoes_cert = _extrair_certidoes_pessoa_combinado(caminho_combinado, rotulo)
    else:
        certidoes, condicoes_cert = _extrair_certidoes_pessoa(form, prefixo, rotulo)
    dados["certidoes"] = certidoes
    condicoes_cert.update(condicoes_cert_conjuge)

    if caminho_combinado:
        try:
            os.unlink(caminho_combinado)
        except OSError:
            pass

    return dados, alertas, condicoes_cert


def _indices_de_partes_presentes(form, grupo: str) -> list[int]:
    """Descobre quantos outorgantes/outorgados vieram no form, olhando
    as chaves que batem com '{grupo}_{indice}_tipo' (ex: 'outorgante_0_tipo',
    'outorgante_1_tipo'...). Isso e' o que permite quantidade variavel de
    partes sem precisar declarar parametro fixo no FastAPI -- o numero de
    outorgantes/outorgados e' decidido pelo que o front realmente mandou,
    sem limite cadastrado no backend."""
    padrao = re.compile(rf"^{re.escape(grupo)}_(\d+)_tipo$")
    indices = set()
    for chave in form.keys():
        m = padrao.match(chave)
        if m:
            indices.add(int(m.group(1)))
    return sorted(indices)


@app.post("/api/processar-documentos")
async def processar_documentos(request: Request, usuario: dict = Depends(exigir_login)):
    """Extrai TODAS as partes (quantos outorgantes e outorgados o caso
    tiver -- sem limite, podendo misturar PF e PJ livremente) + o imovel,
    junto com as certidoes de cada pessoa, e roda as validacoes (digito
    verificador, divergencia de nome) de uma vez, devolvendo tudo pronto
    pra tela de Confirmacao preencher.

    Convencao de nomes dos campos no FormData que o front deve mandar,
    pra cada parte com indice N comecando em 0 (ex: 'outorgante_0',
    'outorgante_1', 'outorgado_0'...):
      {prefixo}_tipo                 -- 'PF' ou 'PJ'
      {prefixo}_doc                  -- documento de identificacao (PF)
      {prefixo}_contrato             -- contrato social (PJ)
      {prefixo}_representante        -- doc. do representante legal (PJ)
      {prefixo}_simplificada         -- certidao simplificada (PJ, opcional)
      {prefixo}_certidao_<tipo_id>   -- uma por tipo fixo de certidao
                                         (ver TIPOS_CERTIDAO em extrair_dados.py)
      {prefixo}_certidao_feitos_comarca_diferente -- repetivel (0, 1 ou mais)

    Mais 'imovel_matricula' (unico, nao tem indice -- so' existe um imovel).
    """
    form = await request.form()

    imovel_matricula = form.get("imovel_matricula")
    imovel_combinado = form.get("imovel_combinado")
    usa_combinado = imovel_combinado is not None and getattr(imovel_combinado, "filename", None)
    if not usa_combinado and (imovel_matricula is None or not getattr(imovel_matricula, "filename", None)):
        raise HTTPException(status_code=400, detail="Matrícula do imóvel não enviada.")

    indices_outorgantes = _indices_de_partes_presentes(form, "outorgante")
    indices_outorgados = _indices_de_partes_presentes(form, "outorgado")

    if not indices_outorgantes:
        raise HTTPException(status_code=400, detail="Nenhum outorgante informado.")
    if not indices_outorgados:
        raise HTTPException(status_code=400, detail="Nenhum outorgado informado.")

    alertas_gerais = []
    condicoes_certidoes = {}

    outorgantes = []
    for posicao, i in enumerate(indices_outorgantes):
        rotulo = f"Outorgante {posicao + 1}" if len(indices_outorgantes) > 1 else "Outorgante"
        dados, alertas, condicoes_cert = _extrair_parte_completa_api(form, f"outorgante_{i}", rotulo)
        outorgantes.append(dados)
        alertas_gerais.extend(alertas)
        # condicoes de certidao ficam com prefixo por posicao pra nao colidir
        # entre outorgantes diferentes (ex: outorgante 1 pode ter dispensado
        # uma certidao que o outorgante 2 apresentou)
        for cid, valor in condicoes_cert.items():
            condicoes_certidoes[f"outorgante_{posicao}_{cid}"] = valor

    outorgados = []
    for posicao, i in enumerate(indices_outorgados):
        rotulo = f"Outorgado {posicao + 1}" if len(indices_outorgados) > 1 else "Outorgado"
        dados, alertas, condicoes_cert = _extrair_parte_completa_api(form, f"outorgado_{i}", rotulo)
        outorgados.append(dados)
        alertas_gerais.extend(alertas)
        for cid, valor in condicoes_cert.items():
            condicoes_certidoes[f"outorgado_{posicao}_{cid}"] = valor

    try:
        caminho_imovel_principal = _salvar_upload_temp(imovel_combinado if usa_combinado else imovel_matricula)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar a matrícula recebida: {e}")

    # Certidao de Ônus separada da matricula -- so' se aplica no modo
    # "documentos separados" (no modo combinado, o onus_vigente ja' veio
    # junto na mesma extracao do imovel abaixo, do mesmo arquivo).
    imovel_onus_arquivo = form.get("imovel_onus")
    tem_onus_separado = not usa_combinado and imovel_onus_arquivo is not None and getattr(imovel_onus_arquivo, "filename", None)
    caminho_onus_separado = _salvar_upload_temp(imovel_onus_arquivo) if tem_onus_separado else None

    # Certidao de IPTU / Tributos Municipais -- no modo combinado, tenta
    # achar no MESMO arquivo da matricula (bastante comum vir tudo junto);
    # no modo separado, usa o arquivo proprio se enviado.
    certidao_municipal_arquivo = form.get("imovel_certidao_municipal")
    caminho_certidao_municipal_separada = (
        _salvar_upload_temp(certidao_municipal_arquivo)
        if not usa_combinado and certidao_municipal_arquivo is not None and getattr(certidao_municipal_arquivo, "filename", None)
        else None
    )

    # BUG ja' corrigido aqui: no modo combinado, a matricula e a certidao de
    # IPTU sao o MESMO arquivo lido duas vezes com schemas diferentes --
    # usar _extrair_e_limpar (que apaga o arquivo logo depois de usar, ver
    # docstring dela) pras duas leituras fazia a SEGUNDA sempre estourar
    # "arquivo nao encontrado", porque a PRIMEIRA ja' tinha apagado o
    # arquivo. Por isso as leituras do modo combinado usam
    # _extrair_sem_apagar (que NUNCA apaga sozinha) e o arquivo so' e'
    # removido manualmente no final, depois de todas as leituras
    # terminarem -- exatamente o mesmo padrao ja' usado pro PDF unico de
    # pessoa. De quebra, roda tudo em PARALELO (matricula + onus separado
    # + certidao municipal, quando aplicaveis, sao leituras independentes).
    tarefas_imovel = {
        "imovel": (caminho_imovel_principal, "imovel", "matrícula do imóvel"),
    }
    if tem_onus_separado:
        tarefas_imovel["onus_separado"] = (caminho_onus_separado, "imovel", "certidão de ônus separada do imóvel")
    if usa_combinado:
        tarefas_imovel["certidao_municipal"] = (
            caminho_imovel_principal, "certidao", "certidão de IPTU (Tributos Municipais) do imóvel",
            _contexto_busca_certidao_especifica("Certidão de IPTU / Tributos Municipais do imóvel"),
        )
    elif caminho_certidao_municipal_separada:
        tarefas_imovel["certidao_municipal"] = (caminho_certidao_municipal_separada, "certidao", "certidão de IPTU (Tributos Municipais) do imóvel")

    resultados_imovel = _extrair_varios_em_paralelo(tarefas_imovel)

    if isinstance(resultados_imovel["imovel"], Exception):
        erro = resultados_imovel["imovel"]
        for caminho in (caminho_imovel_principal, caminho_onus_separado, caminho_certidao_municipal_separada):
            if caminho:
                try:
                    os.unlink(caminho)
                except OSError:
                    pass
        raise erro
    dados_imovel = resultados_imovel["imovel"]

    if tem_onus_separado:
        resultado_onus = resultados_imovel.get("onus_separado")
        if isinstance(resultado_onus, Exception):
            alertas_gerais.append(f"Não foi possível ler a certidão de ônus separada: {resultado_onus}")
        elif resultado_onus.get("onus_vigente"):
            dados_imovel["onus_vigente"] = resultado_onus["onus_vigente"]

    dados_imovel["certidoes_extras"] = {"tributos_municipais": None}
    condicoes_certidoes["imovel_certidao_tributos_municipais_dispensada"] = True
    resultado_cert_municipal = resultados_imovel.get("certidao_municipal")
    if resultado_cert_municipal is not None and not isinstance(resultado_cert_municipal, Exception):
        # No modo combinado, a IA pode simplesmente nao achar essa
        # certidao dentro do arquivo (porque genuinamente nao esta' la')
        # -- nesse caso ela devolve os campos vazios em vez de dar erro.
        # So' aceita o resultado se veio numero OU situacao de verdade;
        # senao mantem certidoes_extras como pendente (nao finge que foi
        # enviada so' porque a chamada nao falhou).
        if resultado_cert_municipal.get("numero") or resultado_cert_municipal.get("situacao"):
            dados_imovel["certidoes_extras"]["tributos_municipais"] = resultado_cert_municipal
            condicoes_certidoes["imovel_certidao_tributos_municipais_dispensada"] = False
    elif isinstance(resultado_cert_municipal, Exception) and not usa_combinado:
        # no modo SEPARADO, a certidao municipal foi um upload proprio e
        # dedicado -- se falhou, e' erro de verdade, nao "nao achei
        # tentando" (diferente do combinado, onde e' so' uma tentativa)
        for caminho in (caminho_imovel_principal, caminho_onus_separado, caminho_certidao_municipal_separada):
            if caminho:
                try:
                    os.unlink(caminho)
                except OSError:
                    pass
        raise resultado_cert_municipal

    for caminho in (caminho_imovel_principal, caminho_onus_separado, caminho_certidao_municipal_separada):
        if caminho:
            try:
                os.unlink(caminho)
            except OSError:
                pass

    for posicao, dados_o in enumerate(outorgantes):
        if dados_o.get("_tipo") == "PF":
            rotulo = f"Outorgante {posicao + 1}" if len(outorgantes) > 1 else "Outorgante"
            alertas_gerais.extend(
                f"{rotulo}: {a}" for a in checar_divergencia_pessoa(dados_o, dados_imovel)
            )
            alerta_regime = _preferir_regime_bens_da_matricula(dados_o, dados_imovel)
            if alerta_regime:
                alertas_gerais.append(f"{rotulo}: {alerta_regime}")

    return {
        "sucesso": True,
        "outorgantes": outorgantes,
        "outorgados": outorgados,
        "dados_imovel": dados_imovel,
        "condicoes_certidoes": condicoes_certidoes,
        "pontos_atencao": alertas_gerais,
    }


@app.post("/api/valor-por-extenso")
def valor_extenso_endpoint(valor: str = Form(...), usuario: dict = Depends(exigir_login)):
    try:
        return {"extenso": valor_por_extenso(valor)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Valor inválido: {e}")


# ---------------------------------------------------------------------------
# HISTORICO
# ---------------------------------------------------------------------------
@app.get("/api/historico/{documento}")
def buscar_historico(documento: str, usuario: dict = Depends(exigir_login)):
    achado = buscar_por_documento(documento)
    if achado:
        return {"encontrado": True, "dados": achado}
    return {"encontrado": False}


# ---------------------------------------------------------------------------
# LOG DE EXTRACOES -- tempo real e tokens gastos por chamada de IA, pra
# medir de verdade (em vez de estimar) e pra achar rapido onde travou/deu
# erro se acontecer de novo.
# ---------------------------------------------------------------------------
@app.get("/api/extracoes/log")
def obter_log_extracoes(limite: int = 50, usuario: dict = Depends(exigir_login)):
    return {"extracoes": listar_extracoes_recentes(limite)}


@app.get("/api/extracoes/tempo-medio")
def obter_tempo_medio_extracoes(usuario: dict = Depends(exigir_login)):
    return tempo_medio_por_tipo()


# ---------------------------------------------------------------------------
# UPLOAD DE MODELO .DOCX PROPRIO -- fluxo alternativo ao motor de itens
# (dados/itens_minuta.json): o usuario sobe o proprio arquivo .docx, com
# as tags «» que ja' usa (concordancia «palavra:N» + variaveis «<NOME>»),
# e o sistema preenche sozinho, sem precisar de configuracao nova por
# minuta -- so' cresce o REGISTRO_VARIAVEIS quando aparecer um nome de
# variavel de verdade novo.
# ---------------------------------------------------------------------------
_PASTA_MODELOS_DOCX = os.path.join(os.path.dirname(__file__), "..", "dados", "modelos_docx")
os.makedirs(_PASTA_MODELOS_DOCX, exist_ok=True)


@app.post("/api/modelos-docx/upload")
async def upload_modelo_docx(nome: str = Form(...), arquivo: UploadFile = None, usuario: dict = Depends(exigir_login)):
    """Salva um .docx enviado pelo usuario como modelo reutilizavel
    (identificado por 'nome', ex: 'compra_e_venda', 'doacao'). Sobrescreve
    se ja existir um modelo com esse nome."""
    if arquivo is None or not getattr(arquivo, "filename", None):
        raise HTTPException(status_code=400, detail="Nenhum arquivo .docx enviado.")
    if not arquivo.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .docx.")

    nome_seguro = re.sub(r"[^a-zA-Z0-9_-]", "_", nome.strip())
    if not nome_seguro:
        raise HTTPException(status_code=400, detail="Nome do modelo inválido.")

    caminho = os.path.join(_PASTA_MODELOS_DOCX, f"{nome_seguro}.docx")
    with open(caminho, "wb") as f:
        f.write(await arquivo.read())

    return {"sucesso": True, "nome": nome_seguro}


@app.get("/api/modelos-docx/listar")
def listar_modelos_docx(usuario: dict = Depends(exigir_login)):
    arquivos = [f[:-5] for f in os.listdir(_PASTA_MODELOS_DOCX) if f.endswith(".docx")]
    return {"modelos": sorted(arquivos)}


@app.post("/api/gerar-minuta-de-modelo-docx")
def gerar_minuta_de_modelo_docx(payload: dict, usuario: dict = Depends(exigir_login)):
    """Preenche o modelo .docx (subido antes via /api/modelos-docx/upload)
    com os dados do caso -- resolve concordancia «palavra:N», variaveis
    «<NOME>» e certidoes «CERTIDAO:tipo» diretamente no arquivo,
    preservando negrito/formatacao de verdade.

    Devolve JSON (nao o arquivo direto) com os avisos e alertas criticos
    encontrados, pra tela poder mostrar isso ANTES do download -- o
    arquivo em si fica pronto num id temporario, baixado depois via
    GET /api/gerar-minuta-de-modelo-docx/download/{arquivo_id}."""
    from minuta_docx_resolver import processar_docx

    nome_modelo = payload.get("nome_modelo")
    contexto = payload.get("contexto", {})

    caminho_modelo = os.path.join(_PASTA_MODELOS_DOCX, f"{nome_modelo}.docx")
    if not os.path.exists(caminho_modelo):
        raise HTTPException(status_code=404, detail=f"Modelo '{nome_modelo}' não encontrado. Envie-o antes em Configurações.")

    perfil = carregar_perfil()
    contexto.setdefault("cartorio", {})
    contexto["cartorio"].update({
        "numero": perfil["cartorio_numero"], "cidade": perfil["cartorio_cidade"], "uf_extenso": perfil["cartorio_uf_extenso"],
    })

    import uuid
    arquivo_id = uuid.uuid4().hex
    caminho_saida = os.path.join(tempfile.gettempdir(), f"minuta_{arquivo_id}.docx")

    try:
        resultado = processar_docx(caminho_modelo, caminho_saida, contexto, payload.get("condicoes", {}))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao preencher o modelo: {e}")

    _ARQUIVOS_MINUTA_GERADA[arquivo_id] = caminho_saida

    # Salva no historico TODAS as partes envolvidas -- alimenta a busca
    # de outorgante recorrente (ver /api/historico/*). Isso estava
    # implementado antes SO' no endpoint antigo (motor JSON), que nao e'
    # mais chamado por nenhum botao da tela -- ou seja, o historico nunca
    # era preenchido de verdade no fluxo real. Movido pra ca'.
    partes_para_salvar = []
    partes_para_salvar.extend(contexto.get("outorgantes") or [])
    partes_para_salvar.extend(contexto.get("outorgados") or [])
    if contexto.get("outorgante"):
        partes_para_salvar.append(contexto["outorgante"])
    if contexto.get("outorgado"):
        partes_para_salvar.append(contexto["outorgado"])
    for p in partes_para_salvar:
        if p:
            try:
                salvar_parte(p)
            except Exception:
                pass  # historico e' um "bonus" -- nunca pode impedir a geracao da minuta

    return {
        "sucesso": True,
        "arquivo_id": arquivo_id,
        "avisos": resultado["avisos"],
        "alertas_criticos": resultado["alertas_criticos"],
    }


# guarda os arquivos gerados aguardando download -- chave e' o arquivo_id,
# valor e' o caminho no disco temporario. Simples de proposito (dict em
# memoria): funciona bem pra 1 instancia do servidor rodando por vez, que
# e' o caso hoje. Se um dia tiver mais de uma instancia/worker, precisa
# virar algo compartilhado (banco, arquivo, redis).
_ARQUIVOS_MINUTA_GERADA: dict[str, str] = {}


@app.get("/api/gerar-minuta-de-modelo-docx/download/{arquivo_id}")
def baixar_minuta_de_modelo_docx(arquivo_id: str, usuario: dict = Depends(exigir_login)):
    caminho_saida = _ARQUIVOS_MINUTA_GERADA.pop(arquivo_id, None)
    if not caminho_saida or not os.path.exists(caminho_saida):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou já baixado. Gere a minuta novamente.")

    from starlette.background import BackgroundTask
    return FileResponse(
        caminho_saida,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="minuta_gerada.docx",
        background=BackgroundTask(lambda: os.remove(caminho_saida) if os.path.exists(caminho_saida) else None),
    )


# ---------------------------------------------------------------------------
# ANALISTA DE MATRICULA (ferramenta isolada)
# ---------------------------------------------------------------------------
def _parsear_data_br(texto: str):
    """Converte 'DD/MM/AAAA' em objeto date. Retorna None se nao
    conseguir (formato inesperado, ou None/vazio) -- nunca lanca erro,
    porque isso e' so' pra enriquecer o relatorio, nunca pode quebrar a
    analise principal por causa de uma data mal formatada."""
    if not texto or not isinstance(texto, str):
        return None
    from datetime import datetime as _dt
    for formato in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return _dt.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


@app.post("/api/analisar-matricula")
def analisar_matricula(arquivo: UploadFile = None, usuario: dict = Depends(exigir_login)):
    if arquivo is None:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    try:
        caminho = _salvar_upload_temp(arquivo)
        resultado = _extrair_e_limpar(caminho, "imovel")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar matrícula: {e}")

    from datetime import timedelta

    agora = datetime.now(timezone.utc)
    meta = {
        "analisado_em": agora.isoformat(),
        "analisado_por": usuario.get("nome_completo") or usuario.get("username"),
    }

    # Validade da certidao -- regra dos 30 dias, calculada a partir da
    # data de emissao QUE A PROPRIA CERTIDAO TRAZ (nao da data de hoje
    # sozinha -- precisa da data extraida do documento pra funcionar).
    data_emissao = _parsear_data_br(resultado.get("data_emissao_certidao"))
    if data_emissao:
        dias_passados = (date.today() - data_emissao).days
        meta["certidao_validade"] = {
            "data_emissao": resultado.get("data_emissao_certidao"),
            "dias_passados": dias_passados,
            "dentro_do_prazo": dias_passados <= 30,
        }
    else:
        meta["certidao_validade"] = None

    # Alerta de "matricula desatualizada" -- se a ultima mudanca relevante
    # (transmissao, novo onus, baixa de onus, mudanca de estado civil) foi
    # ha' muito tempo, vale sugerir confirmar se o estado civil dos
    # proprietarios ainda e' o mesmo (pode ter mudado sem constar ainda).
    data_ultima_alteracao = _parsear_data_br(resultado.get("data_ultima_alteracao_relevante"))
    if data_ultima_alteracao:
        dias_desde_alteracao = (date.today() - data_ultima_alteracao).days
        meta["matricula_desatualizada"] = dias_desde_alteracao > 180
        meta["dias_desde_ultima_alteracao"] = dias_desde_alteracao
    else:
        meta["matricula_desatualizada"] = False
        meta["dias_desde_ultima_alteracao"] = None

    return {"sucesso": True, "resultado": resultado, "meta": meta}


# ---------------------------------------------------------------------------
# GERACAO DE MINUTA (motor real -- ver gerar_minuta_de_modelo_docx acima)
# ---------------------------------------------------------------------------
# NOTA: os antigos endpoints /api/gerar-minuta e /api/gerar-minuta-docx
# (motor JSON por item, dados/itens_minuta.json) foram removidos daqui --
# nenhum botao da tela os chamava havia tempo (o fluxo real e' 100%
# baseado no .docx que o usuario sobe, via gerar_minuta_de_modelo_docx
# acima). O modulo motor_minuta.py continua existindo porque
# minuta_docx_resolver.py reusa _substituir_variaveis dele.


@app.get("/api/perfil")
def obter_perfil(usuario: dict = Depends(exigir_login)):
    return carregar_perfil()


@app.put("/api/perfil")
def atualizar_perfil(payload: dict, usuario: dict = Depends(exigir_login)):
    salvar_perfil(payload)
    return {"sucesso": True}

    def _nomes_das_partes(lista_partes, singular) -> str:
        nomes = [p.get("nome") or p.get("razao_social") or "" for p in (lista_partes or []) if p]
        if not nomes and singular:
            nomes = [(singular.get("nome") or singular.get("razao_social") or "")]
        return "; ".join(n for n in nomes if n)

    outorgante_nome = _nomes_das_partes(contexto.get("outorgantes"), contexto.get("outorgante"))
    outorgado_nome = _nomes_das_partes(contexto.get("outorgados"), contexto.get("outorgado"))
    registrar_minuta(tipo_ato, outorgante_nome, outorgado_nome)

    return FileResponse(
        saida_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="minuta_compra_venda.docx",
        headers={"X-Avisos": str(len(avisos))},
        background=BackgroundTask(lambda: os.path.exists(saida_path) and os.unlink(saida_path)),
    )


# ---------------------------------------------------------------------------
# SERVE O MOCKUP (front) na raiz -- mesma origem da API, sem CORS pra
# resolver na hora de testar local
# ---------------------------------------------------------------------------
_MOCKUP_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")

@app.get("/api/estatisticas")
def obter_estatisticas(usuario: dict = Depends(exigir_login)):
    return {
        "minutas_geradas_mes": contar_minutas_mes(),
        "minutas_geradas_total": contar_minutas_total(),
        "atividade_recente": listar_atividade_recente(10),
    }


@app.get("/")
def servir_mockup():
    if os.path.exists(_MOCKUP_PATH):
        return FileResponse(_MOCKUP_PATH)
    return JSONResponse({"erro": "mockup nao encontrado em " + _MOCKUP_PATH}, status_code=404)


# ---------------------------------------------------------------------------
# CONFIGURACOES -- biblioteca de itens e composicao por tipo de ato
# ---------------------------------------------------------------------------
@app.get("/api/modelos")
def listar_modelos(usuario: dict = Depends(exigir_login)):
    return listar_modelos_disponiveis()


@app.get("/api/modelos/{tipo_ato}")
def ver_modelo(tipo_ato: str, usuario: dict = Depends(exigir_login)):
    try:
        return obter_modelo(tipo_ato)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/modelos")
def criar_modelo_endpoint(payload: dict, usuario: dict = Depends(exigir_login)):
    tipo_ato = payload.get("tipo_ato")
    nome = payload.get("nome")
    if not tipo_ato or not nome:
        raise HTTPException(status_code=400, detail="tipo_ato e nome são obrigatórios.")
    try:
        criar_modelo(tipo_ato, nome)
        return {"sucesso": True}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put("/api/modelos/{tipo_ato}/itens/{item_id}")
def salvar_item_endpoint(tipo_ato: str, item_id: str, payload: dict, usuario: dict = Depends(exigir_login)):
    try:
        salvar_item(tipo_ato, item_id, payload)
        return {"sucesso": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/modelos/{tipo_ato}/itens/{item_id}")
def remover_item_endpoint(tipo_ato: str, item_id: str, usuario: dict = Depends(exigir_login)):
    try:
        remover_item(tipo_ato, item_id)
        return {"sucesso": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/api/modelos/{tipo_ato}/ordem")
def salvar_ordem_endpoint(tipo_ato: str, payload: dict, usuario: dict = Depends(exigir_login)):
    ordem = payload.get("ordem", [])
    try:
        salvar_ordem(tipo_ato, ordem)
        return {"sucesso": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
