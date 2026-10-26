"""
Copiloto Notarial -- interface web com login.

RODAR:
    streamlit run app.py

Antes de rodar pela primeira vez, crie ao menos um usuário:
    python3 scripts/criar_usuario.py
"""
import streamlit as st
import sys
import os
import tempfile
import json

# Ponte pro Streamlit Community Cloud: la' a chave de API e' configurada
# como "secret" na plataforma (st.secrets), nao como variavel de ambiente
# do sistema operacional. Local continua funcionando igual, via
# ANTHROPIC_API_KEY no ambiente -- esse bloco so' entra em acao quando
# existir um secrets.toml configurado (na nuvem), sem quebrar nada local.
try:
    if "ANTHROPIC_API_KEY" in st.secrets and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass  # sem secrets.toml (rodando local) -- segue usando o ambiente normal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from auth import verificar_login, criar_usuario
from extrair_dados import extrair, verificar_consolidacao_pj
from validadores import validar_cpf, validar_cnpj, valor_por_extenso
from consistencia import checar_divergencia_pessoa
from historico import salvar_parte, buscar_por_documento
from motor_minuta import montar_minuta
from docx import Document

st.set_page_config(page_title="Copiloto Notarial", page_icon="📜", layout="centered")


def aplicar_estilo():
    """Injeta a identidade visual completa (mesma paleta e fontes do
    mockup) por cima do tema padrao do Streamlit. Isso e' CSS/HTML puro
    via st.markdown -- nao muda nenhuma logica do app, so' a aparencia."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {
            --preto: #0B1220;
            --grafite: #131C2E;
            --grafite-claro: #2A3548;
            --verde-sinal: #38BDF8;
            --azul-onda: #6FA8DC;
            --bruma: #F1F5F9;
            --texto-sec: #94A3B8;
            --botao: #0B5FA5;
            --botao-hover: #136FBD;
        }

        .stApp {
            background-color: var(--preto);
            background-image:
                linear-gradient(rgba(148,163,184,0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(148,163,184,0.05) 1px, transparent 1px),
                radial-gradient(circle at 12% 0%, rgba(56,189,248,0.10) 0%, transparent 45%),
                radial-gradient(circle at 88% 100%, rgba(111,168,220,0.08) 0%, transparent 45%);
            background-size: 30px 30px, 30px 30px, 100% 100%, 100% 100%;
            font-family: 'IBM Plex Sans', sans-serif;
        }

        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif !important;
            color: var(--bruma) !important;
        }
        h1 { font-size: 1.9rem !important; }
        p, span, label, div { color: var(--bruma); }
        .stCaption, [data-testid="stCaptionContainer"] { color: var(--texto-sec) !important; }

        /* Cartao ao redor do formulario de login */
        div[data-testid="stForm"] {
            background: var(--grafite);
            border: 1px solid var(--grafite-claro);
            border-radius: 10px;
            padding: 28px 26px 12px;
            position: relative;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        div[data-testid="stForm"]::before {
            content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
            border-radius: 10px 10px 0 0;
            background: linear-gradient(90deg, transparent, var(--verde-sinal), var(--azul-onda), transparent);
        }

        /* Campos de texto */
        input, textarea {
            background-color: #0D1526 !important;
            color: var(--bruma) !important;
            border: 1px solid #3A4759 !important;
            border-radius: 6px !important;
        }
        input:focus, textarea:focus {
            border-color: var(--verde-sinal) !important;
            box-shadow: 0 0 0 2px rgba(56,189,248,0.25) !important;
        }

        /* Botoes solidos, mesma cor de acao do mockup */
        .stButton button, .stFormSubmitButton button, .stDownloadButton button {
            background-color: var(--botao) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
        }
        .stButton button:hover, .stFormSubmitButton button:hover, .stDownloadButton button:hover {
            background-color: var(--botao-hover) !important;
        }

        /* Sidebar / abas */
        section[data-testid="stSidebar"] {
            background-color: var(--grafite) !important;
            border-right: 1px solid var(--grafite-claro);
        }
        button[data-baseweb="tab"] { color: var(--texto-sec) !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: var(--verde-sinal) !important; }
        div[data-baseweb="tab-highlight"] { background-color: var(--verde-sinal) !important; }

        /* Cartoes de expander/secao */
        div[data-testid="stExpander"] {
            background: var(--grafite);
            border: 1px solid var(--grafite-claro);
            border-radius: 8px;
        }
        </style>

        <div style="text-align:center; margin-bottom: -10px;">
          <svg width="37" height="57" viewBox="0 0 60 92" fill="none">
            <line x1="14" y1="9" x2="14" y2="40" stroke="#38BDF8" stroke-width="3.2" stroke-linecap="square"/>
            <line x1="14" y1="9" x2="46" y2="53" stroke="#38BDF8" stroke-width="3.2" stroke-linecap="square"/>
            <line x1="46" y1="9" x2="46" y2="56" stroke="#38BDF8" stroke-width="3.2" stroke-linecap="square"/>
            <path d="M14 40 L18.5 48 L15 89 L14 89 L10.5 48 Z" stroke="#38BDF8" stroke-width="1.7" stroke-linejoin="round"/>
            <line x1="14.5" y1="50" x2="14.5" y2="82" stroke="#0B1220" stroke-width="1"/>
            <rect x="12.7" y="57.2" width="3.6" height="3.6" transform="rotate(45 14.5 59)" fill="#6FA8DC"/>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )



# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------
def tela_login():
    aplicar_estilo()
    _, col_meio, _ = st.columns([1, 1.3, 1])
    with col_meio:
        st.title("Copiloto Notarial")
        st.caption("Você decide. Ele digita.")
        st.divider()

        with st.form("login"):
            username = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            usuario = verificar_login(username, senha)
            if usuario:
                st.session_state["usuario"] = usuario
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

        with st.expander("Primeiro acesso? Criar conta"):
            with st.form("criar_conta"):
                novo_nome = st.text_input("Seu nome")
                novo_cartorio = st.text_input("Nome do cartório")
                novo_username = st.text_input("Escolha um usuário")
                nova_senha = st.text_input("Escolha uma senha", type="password")
                criar = st.form_submit_button("Criar conta")

        if criar:
            if not novo_username or not nova_senha:
                st.error("Preencha usuário e senha.")
            elif criar_usuario(novo_username, nova_senha, novo_nome, novo_cartorio):
                st.success("Conta criada! Agora é só entrar com usuário e senha ali em cima.")
            else:
                st.error("Esse nome de usuário já existe — escolha outro.")


# ---------------------------------------------------------------------------
# APP PRINCIPAL (pos-login)
# ---------------------------------------------------------------------------
def salvar_upload_temp(arquivo_upload):
    if arquivo_upload is None:
        return None
    sufixo = "." + arquivo_upload.name.split(".")[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
        tmp.write(arquivo_upload.read())
        return tmp.name


def bloco_documentos_parte(rotulo: str, key_prefix: str) -> dict:
    """Mostra a chave PF/PJ pra uma parte (vendedor ou comprador) e os
    uploads certos conforme a escolha -- e' o toggle que estava so de
    enfeite no mockup, aqui ele de fato troca quais arquivos sao pedidos."""
    st.markdown(f"**{rotulo}**")
    tipo = st.radio(
        f"Tipo — {rotulo}",
        ["Pessoa Física", "Pessoa Jurídica"],
        key=f"{key_prefix}_tipo",
        horizontal=True,
        label_visibility="collapsed",
    )
    arquivos = {"tipo": "PF" if tipo == "Pessoa Física" else "PJ"}

    if tipo == "Pessoa Física":
        arquivos["doc_pessoal"] = st.file_uploader(
            "Documento de identificação (RG/CPF)",
            type=["jpg", "jpeg", "png", "pdf"],
            key=f"{key_prefix}_pf_doc",
        )
    else:
        arquivos["contrato_social"] = st.file_uploader(
            "Contrato Social ou Estatuto",
            type=["jpg", "jpeg", "png", "pdf"],
            key=f"{key_prefix}_pj_contrato",
        )
        arquivos["certidao_simplificada"] = st.file_uploader(
            "Certidão Simplificada (Junta Comercial) — recomendada",
            type=["jpg", "jpeg", "png", "pdf"],
            key=f"{key_prefix}_pj_simplificada",
            help="Sem ela, não dá pra confirmar se o Contrato Social apresentado é o mais atual.",
        )
        arquivos["doc_representante"] = st.file_uploader(
            "Documento de identificação do representante legal",
            type=["jpg", "jpeg", "png", "pdf"],
            key=f"{key_prefix}_pj_representante",
        )
    return arquivos


def parte_completa(arquivos: dict) -> bool:
    if arquivos["tipo"] == "PF":
        return arquivos.get("doc_pessoal") is not None
    return arquivos.get("contrato_social") is not None and arquivos.get("doc_representante") is not None


def extrair_parte(arquivos: dict, rotulo: str) -> tuple[dict, list[str]]:
    """Extrai os dados de uma parte (PF ou PJ) e retorna (dados, pontos_de_atencao)."""
    if arquivos["tipo"] == "PF":
        caminho = salvar_upload_temp(arquivos["doc_pessoal"])
        dados = extrair(caminho, "pessoa")
        dados["_tipo"] = "PF"
        return dados, []

    caminho_contrato = salvar_upload_temp(arquivos["contrato_social"])
    dados = extrair(caminho_contrato, "pessoa_juridica")
    dados["_tipo"] = "PJ"

    dados_simplificada = None
    if arquivos.get("certidao_simplificada"):
        caminho_simpl = salvar_upload_temp(arquivos["certidao_simplificada"])
        dados_simplificada = extrair(caminho_simpl, "certidao_simplificada")

    alertas = verificar_consolidacao_pj(dados, dados_simplificada)
    alertas = [f"{rotulo}: {a}" for a in alertas]

    if arquivos.get("doc_representante"):
        caminho_rep = salvar_upload_temp(arquivos["doc_representante"])
        dados["representante"] = extrair(caminho_rep, "pessoa")

    return dados, alertas


def tela_analista_matricula():
    """Ferramenta independente do fluxo de minuta -- so' analisa uma
    matricula avulsa e devolve o relatorio (situacao juridica, onus
    vigente, ajuste de descricao futuro->presente, alertas internos).
    Util pra checar um imovel antes mesmo de decidir seguir com o ato."""
    st.subheader("🔍 Analista de Matrícula")
    st.caption("Envie uma matrícula e receba a situação jurídica atualizada, sem precisar estar no meio de uma minuta.")

    doc = st.file_uploader("Certidão de matrícula", type=["jpg", "jpeg", "png", "pdf"], key="analista_matricula_doc")

    if st.button("Analisar matrícula", type="primary", disabled=doc is None):
        with st.spinner("Lendo os registros e averbações em ordem cronológica... (pode levar mais tempo que uma extração simples)"):
            try:
                caminho = salvar_upload_temp(doc)
                st.session_state["analista_resultado"] = extrair(caminho, "imovel")
            except Exception as e:
                st.error(f"Erro ao analisar matrícula: {e}")

    resultado = st.session_state.get("analista_resultado")
    if resultado:
        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Proprietário(s) atual(is)**")
            st.write(resultado.get("proprietario_atual") or "não identificado")
            st.markdown("**Matrícula / Ofício**")
            st.write(f"{resultado.get('matricula', '—')} — {resultado.get('oficio_registro', '—')}")
            st.markdown("**Comarca / Circunscrição**")
            st.write(f"{resultado.get('comarca', '—')} / {resultado.get('circunscricao', '—')}")
        with col_b:
            st.markdown("**Ônus vigente**")
            onus = resultado.get("onus_vigente")
            if onus and onus != "nenhum":
                st.error(onus if isinstance(onus, str) else ", ".join(onus))
            else:
                st.success("Nenhum ônus vigente identificado")
            st.markdown("**Descrição ajustada (futuro → presente)?**")
            st.write("Sim — obra concluída identificada" if resultado.get("descricao_ajustada_de_futuro_para_presente") == "sim" else "Não se aplica")

        st.markdown("**Descrição atual do imóvel**")
        st.write(resultado.get("descricao") or "—")

        alertas = resultado.get("alertas_internos_matricula")
        if alertas and alertas != "nenhum":
            st.warning("**⚠ Alertas internos da matrícula**\n\n" + (
                "\n".join(f"- {a}" for a in alertas) if isinstance(alertas, list) else f"- {alertas}"
            ))

        with st.expander("Ver todos os campos extraídos (JSON)"):
            st.json(resultado)


def dados_imovel_onus_resumo(dados_imovel: dict) -> str:
    """Pega o campo onus_vigente (que pode vir como lista ou string da
    extracao) e devolve um resumo curto pro texto da minuta -- so' o
    apontamento (ex: 'hipoteca'), sem numero de processo/credor, como
    combinado."""
    onus = dados_imovel.get("onus_vigente") or dados_imovel.get("onus")
    if not onus or onus == "nenhum":
        return "ônus identificado"
    if isinstance(onus, list):
        return ", ".join(str(o) for o in onus)
    return str(onus)


def tela_nova_minuta():
    usuario = st.session_state["usuario"]

    st.divider()
    st.subheader("0. Tipo de ato")
    tipo_ato_label = st.selectbox(
        "Tipo de ato",
        [
            "Compra e Venda à Vista",
            "Compra e Venda com Cláusula Resolutiva",
            "Doação Plena",
            "Doação com Reserva de Usufruto",
            "Dação em Pagamento",
            "Inventário com Partilha de Bem",
            "Inventário com Adjudicação de Bem",
            "Nomeação de Inventariante",
            "Renúncia de Direitos Hereditários",
            "Renúncia de Usufruto",
        ],
        label_visibility="collapsed",
    )
    tipo_ato_id = "compra_e_venda_a_vista" if tipo_ato_label == "Compra e Venda à Vista" else None
    if tipo_ato_id is None:
        st.info(f"'{tipo_ato_label}' ainda não tem composição de itens cadastrada em Configurações → Modelos de minuta. Você pode seguir extraindo os documentos, mas a geração final da minuta não estará disponível pra esse tipo ainda.")

    st.divider()
    st.subheader("1. Envie os documentos")

    c1, c2 = st.columns(2)
    with c1:
        with st.expander("🔎 Já é cliente? Buscar por CPF/CNPJ", expanded=False):
            busca_v = st.text_input("CPF/CNPJ do vendedor", key="busca_vendedor")
            if st.button("Buscar", key="btn_busca_vendedor") and busca_v:
                achado = buscar_por_documento(busca_v)
                if achado:
                    st.session_state["dados_vendedor_historico"] = achado
                    st.success(f"Encontrado: {achado.get('nome') or achado.get('razao_social')} (atualizado em {achado.get('_atualizado_em', '—')[:10]})")
                else:
                    st.warning("Nenhum registro encontrado com esse documento.")
        arqs_vendedor = bloco_documentos_parte("Vendedor", "vendedor")
    with c2:
        with st.expander("🔎 Já é cliente? Buscar por CPF/CNPJ", expanded=False):
            busca_c = st.text_input("CPF/CNPJ do comprador", key="busca_comprador")
            if st.button("Buscar", key="btn_busca_comprador") and busca_c:
                achado = buscar_por_documento(busca_c)
                if achado:
                    st.session_state["dados_comprador_historico"] = achado
                    st.success(f"Encontrado: {achado.get('nome') or achado.get('razao_social')} (atualizado em {achado.get('_atualizado_em', '—')[:10]})")
                else:
                    st.warning("Nenhum registro encontrado com esse documento.")
        arqs_comprador = bloco_documentos_parte("Comprador", "comprador")
    doc_matricula = st.file_uploader("Certidão de matrícula do imóvel", type=["jpg", "jpeg", "png", "pdf"], key="matricula")

    pronto = (
        (parte_completa(arqs_vendedor) or "dados_vendedor_historico" in st.session_state)
        and (parte_completa(arqs_comprador) or "dados_comprador_historico" in st.session_state)
        and doc_matricula is not None
    )

    if st.button("Extrair dados dos documentos", type="primary", disabled=not pronto):
        with st.spinner("Lendo documentos..."):
            try:
                if "dados_vendedor_historico" in st.session_state:
                    dados_vendedor, alertas_vendedor = dict(st.session_state["dados_vendedor_historico"]), []
                else:
                    dados_vendedor, alertas_vendedor = extrair_parte(arqs_vendedor, "Vendedor")

                if "dados_comprador_historico" in st.session_state:
                    dados_comprador, alertas_comprador = dict(st.session_state["dados_comprador_historico"]), []
                else:
                    dados_comprador, alertas_comprador = extrair_parte(arqs_comprador, "Comprador")

                caminho_m = salvar_upload_temp(doc_matricula)
                dados_imovel = extrair(caminho_m, "imovel")

                alertas_gerais = []

                # Validacao de digito verificador -- zero custo de IA, pega
                # erro de OCR/digito trocado antes de qualquer outra coisa.
                for rotulo, d in (("Vendedor", dados_vendedor), ("Comprador", dados_comprador)):
                    if d.get("_tipo") == "PJ":
                        if d.get("cnpj") and not validar_cnpj(d["cnpj"]):
                            alertas_gerais.append(f"{rotulo}: CNPJ '{d['cnpj']}' tem dígito verificador inválido — provável erro de leitura, confira o documento original.")
                    else:
                        if d.get("cpf") and not validar_cpf(d["cpf"]):
                            alertas_gerais.append(f"{rotulo}: CPF '{d['cpf']}' tem dígito verificador inválido — provável erro de leitura, confira o documento original.")

                # Divergencia de nome entre documento de identificacao e matricula
                # (so' faz sentido pro vendedor, que e' o outorgante/proprietario)
                if dados_vendedor.get("_tipo") == "PF":
                    alertas_gerais.extend(checar_divergencia_pessoa(dados_vendedor, dados_imovel))

                st.session_state["dados_vendedor"] = dados_vendedor
                st.session_state["dados_comprador"] = dados_comprador
                st.session_state["dados_imovel"] = dados_imovel
                st.session_state["tipo_ato_id"] = tipo_ato_id
                st.session_state["pontos_atencao"] = alertas_gerais + alertas_vendedor + alertas_comprador
                st.success("Dados extraídos. Confira e corrija abaixo antes de gerar a minuta.")
            except Exception as e:
                st.error(f"Erro ao extrair dados: {e}")

    if st.session_state.get("pontos_atencao"):
        st.warning("**⚠ Pontos de atenção**\n\n" + "\n\n".join(f"- {a}" for a in st.session_state["pontos_atencao"]))

    if "dados_vendedor" in st.session_state:
        st.divider()
        st.subheader("2. Confira e corrija os dados extraídos")
        st.caption("A IA pode errar — confira cada campo antes de gerar a minuta.")

        with st.expander("Vendedor", expanded=True):
            dv = st.session_state["dados_vendedor"]
            exige_outorga = False
            if dv.get("_tipo") == "PJ":
                dv["razao_social"] = st.text_input("Razão social", dv.get("razao_social", ""), key="v_rs")
                dv["cnpj"] = st.text_input("CNPJ", dv.get("cnpj", ""), key="v_cnpj")
                dv["endereco_sede"] = st.text_input("Endereço da sede", dv.get("endereco_sede", ""), key="v_end_pj")
                dv["nome_representante_legal"] = st.text_input("Representante legal", dv.get("nome_representante_legal", ""), key="v_rep")
                dv["poderes_representante"] = st.text_input("Poderes do representante", dv.get("poderes_representante", ""), key="v_poderes")
                st.caption("A redação da minuta para Pessoa Jurídica ainda depende do modelo específico ser cadastrado em Configurações → Modelos de minuta.")
            else:
                dv["nome"] = st.text_input("Nome", dv.get("nome", ""), key="v_nome")
                dv["estado_civil"] = st.text_input("Estado civil", dv.get("estado_civil", ""), key="v_ec")
                dv["cpf"] = st.text_input("CPF", dv.get("cpf", ""), key="v_cpf")
                dv["rg"] = st.text_input("RG", dv.get("rg", ""), key="v_rg")
                dv["orgao_expedidor"] = st.text_input("Órgão expedidor", dv.get("orgao_expedidor", ""), key="v_org")
                dv["profissao"] = st.text_input("Profissão", dv.get("profissao", ""), key="v_prof")
                dv["endereco"] = st.text_input("Endereço", dv.get("endereco", ""), key="v_end")
                dv["nacionalidade"] = st.text_input("Nacionalidade", dv.get("nacionalidade", "brasileiro(a)"), key="v_nac")
                exige_outorga = st.checkbox("Regime de bens exige outorga do cônjuge", key="v_outorga")

        with st.expander("Comprador", expanded=True):
            dc = st.session_state["dados_comprador"]
            if dc.get("_tipo") == "PJ":
                dc["razao_social"] = st.text_input("Razão social", dc.get("razao_social", ""), key="c_rs")
                dc["cnpj"] = st.text_input("CNPJ", dc.get("cnpj", ""), key="c_cnpj")
                dc["endereco_sede"] = st.text_input("Endereço da sede", dc.get("endereco_sede", ""), key="c_end_pj")
                dc["nome_representante_legal"] = st.text_input("Representante legal", dc.get("nome_representante_legal", ""), key="c_rep")
                dc["poderes_representante"] = st.text_input("Poderes do representante", dc.get("poderes_representante", ""), key="c_poderes")
            else:
                dc["nome"] = st.text_input("Nome", dc.get("nome", ""), key="c_nome")
                dc["estado_civil"] = st.text_input("Estado civil", dc.get("estado_civil", ""), key="c_ec")
                dc["cpf"] = st.text_input("CPF", dc.get("cpf", ""), key="c_cpf")
                dc["rg"] = st.text_input("RG", dc.get("rg", ""), key="c_rg")
                dc["orgao_expedidor"] = st.text_input("Órgão expedidor", dc.get("orgao_expedidor", ""), key="c_org")
                dc["profissao"] = st.text_input("Profissão", dc.get("profissao", ""), key="c_prof")
                dc["endereco"] = st.text_input("Endereço", dc.get("endereco", ""), key="c_end")
                dc["nacionalidade"] = st.text_input("Nacionalidade", dc.get("nacionalidade", "brasileiro(a)"), key="c_nac")

        with st.expander("Imóvel", expanded=True):
            di = st.session_state["dados_imovel"]
            di["descricao"] = st.text_input("Descrição", di.get("descricao", ""), key="i_desc")
            di["endereco"] = st.text_input("Endereço", di.get("endereco", ""), key="i_end")
            di["matricula"] = st.text_input("Matrícula nº", di.get("matricula", ""), key="i_mat")
            di["oficio_registro"] = st.text_input("Ofício de Registro", di.get("oficio_registro", ""), key="i_of")
            di["area"] = st.text_input("Área", di.get("area", ""), key="i_area")
            di["inscricao_iptu"] = st.text_input("Inscrição IPTU", di.get("inscricao_iptu", ""), key="i_iptu")
            di["titulo_aquisitivo"] = st.text_input("Título aquisitivo", di.get("titulo_aquisitivo", ""), key="i_titulo")

        st.divider()
        st.subheader("3. Dados do negócio")

        neg_col1, neg_col2 = st.columns(2)
        with neg_col1:
            valor_numerico = st.text_input("Valor da transação (R$)", "", key="neg_valor_num")
        with neg_col2:
            pago_no_ato = st.radio(
                "Forma de pagamento",
                ["Pago anteriormente em espécie", "Pago neste ato"],
                horizontal=True,
                key="neg_forma_pagto",
            ) == "Pago neste ato"

        # Valor por extenso automatico -- elimina a digitacao duplicada e a
        # chance do numero e o extenso nao baterem entre si.
        valor_extenso = ""
        if valor_numerico:
            try:
                valor_extenso = valor_por_extenso(valor_numerico)
                st.caption(f"Por extenso: *{valor_extenso}*")
            except Exception:
                st.caption("Não foi possível calcular o valor por extenso — confira o formato digitado.")

        st.markdown("**Condições que afetam a redação (marque o que se aplica a este caso)**")
        cond_col1, cond_col2 = st.columns(2)
        with cond_col1:
            onus_existe = st.checkbox("Há ônus vigente na matrícula (ex: hipoteca)", key="cond_onus_existe")
            onus_dispensado = st.checkbox("Certidão de ônus não apresentada (dispensada)", key="cond_onus_disp")
        with cond_col2:
            certidoes_dispensadas = st.checkbox("Alguma certidão de feitos ajuizados/tributos não apresentada", key="cond_cert_disp")
            imovel_em_condominio = st.checkbox("Imóvel é unidade em condomínio/edifício", key="cond_condominio")

        lista_certidoes_faltantes = ""
        if certidoes_dispensadas:
            lista_certidoes_faltantes = st.text_input(
                "Quais certidões faltaram (vai dentro do texto de dispensa)",
                "feitos ajuizados Cíveis e Execuções fiscais",
                key="cond_lista_certidoes",
            )

        cartorio_nome = st.text_input("Nome do tabelionato", usuario["cartorio"] or "")
        data_ato = st.text_input("Data do ato (por extenso)", "")

        st.divider()
        if any(d.get("_tipo") == "PJ" for d in (dv, dc)):
            st.info(
                "Uma ou ambas as partes são Pessoa Jurídica — as variantes de "
                "PJ já cadastradas no Item 12 serão aplicadas automaticamente."
            )

        gerar_disponivel = tipo_ato_id is not None
        if not gerar_disponivel:
            st.warning(f"Geração ainda não disponível para '{tipo_ato_label}' — falta cadastrar a composição de itens desse tipo de ato.")

        if st.button("Gerar minuta", type="primary", disabled=not gerar_disponivel):
            # Normalizacao minima pra PJ nao gerar campo vazio onde o motor
            # espera "nome" -- nao substitui a redacao juridica de PJ em si.
            for parte in (dv, dc):
                if parte.get("_tipo") == "PJ" and not parte.get("nome"):
                    parte["nome"] = parte.get("razao_social", "")
                    parte["cpf"] = parte.get("cnpj", "")

            contexto = {
                "outorgante": dv,
                "outorgado": dc,
                "imovel": di,
                "matricula": {"data_expedicao": di.get("data_expedicao", "")},
                "cartorio": {"numero": "", "cidade": cartorio_nome, "uf_extenso": ""},
                "tabeliao": {"nome": usuario["nome_completo"], "cargo": "Tabeliã(o) de Notas"},
                "ordem_lavratura": "",
                "data_lavratura": data_ato,
                "onus": {"descricao_resumida": dados_imovel_onus_resumo(di)},
                "iptu": {"certidao_numero": "", "certidao_data": "", "certidao_validade": ""},
                "lista_certidoes_faltantes": lista_certidoes_faltantes,
            }
            condicoes = {
                "onus_existe": onus_existe,
                "onus_dispensado": onus_dispensado,
                "certidoes_dispensadas": certidoes_dispensadas,
                "imovel_em_condominio": imovel_em_condominio,
                "outorgante_pf": dv.get("_tipo") != "PJ",
                "outorgado_pj": dc.get("_tipo") == "PJ",
                "pago_no_ato": pago_no_ato,
            }

            try:
                texto_minuta, avisos_motor = montar_minuta(tipo_ato_id, contexto, condicoes)
            except Exception as e:
                st.error(f"Erro ao montar a minuta: {e}")
                texto_minuta, avisos_motor = None, []

            if texto_minuta:
                if avisos_motor:
                    st.warning("**⚠ Pontos de atenção da montagem**\n\n" + "\n\n".join(f"- {a}" for a in avisos_motor))

                doc = Document()
                doc.add_heading("ESCRITURA PÚBLICA DE VENDA E COMPRA", level=1)
                for bloco in texto_minuta.split("\n\n"):
                    for linha in bloco.split("\n"):
                        doc.add_paragraph(linha)

                saida_path = os.path.join(tempfile.gettempdir(), f"minuta_{usuario['username']}.docx")
                doc.save(saida_path)

                # Salva as partes no historico pra reaproveitar num proximo caso
                salvar_parte(dv)
                salvar_parte(dc)

                with open(saida_path, "rb") as f:
                    st.download_button(
                        "Baixar minuta gerada (.docx)",
                        f.read(),
                        file_name="minuta_compra_venda.docx",
                        type="primary",
                    )

                with st.expander("Ver texto completo montado"):
                    st.text(texto_minuta)


def tela_app():
    aplicar_estilo()
    usuario = st.session_state["usuario"]

    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("📜 Copiloto Notarial")
        st.caption(f"Logado como {usuario['nome_completo'] or usuario['username']} — {usuario['cartorio']}")
    with col2:
        if st.button("Sair"):
            del st.session_state["usuario"]
            st.rerun()

    aba_minuta, aba_matricula = st.tabs(["📝 Nova Minuta", "🔍 Analista de Matrícula"])
    with aba_minuta:
        tela_nova_minuta()
    with aba_matricula:
        tela_analista_matricula()


# ---------------------------------------------------------------------------
if "usuario" not in st.session_state:
    tela_login()
else:
    tela_app()
