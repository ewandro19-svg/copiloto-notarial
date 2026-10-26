"""
Gera documentos FICTICIOS (RG/CPF, matricula de imovel, certidoes) pra
testar o Copiloto Notarial sem precisar usar documento de pessoa real.

Todo documento gerado aqui:
  - Tem dado 100% inventado (nome, CPF, numero de matricula, etc. -- nada
    corresponde a pessoa ou imovel real).
  - Traz uma marca d'agua e um aviso explicito "DOCUMENTO FICTICIO --
    SEM VALIDADE LEGAL, USO EXCLUSIVO PARA TESTES DE SOFTWARE" em
    destaque, pra nao ter risco nenhum de ser confundido com documento
    de verdade nem usado indevidamente.
  - NAO tenta reproduzir selo oficial, QR code de validacao, brasao de
    orgao publico, ou qualquer elemento de seguranca -- e' so' um layout
    simples com os campos de texto que a extracao por IA precisa ler,
    suficiente pra testar o pipeline (upload -> extracao -> minuta).

USO (linha de comando):
    python3 gerar_documentos_teste.py rg
    python3 gerar_documentos_teste.py matricula --onus alienacao_fiduciaria
    python3 gerar_documentos_teste.py matricula --sem-onus
    python3 gerar_documentos_teste.py certidao --tipo tributos_federais --situacao negativa
    python3 gerar_documentos_teste.py certidao --tipo debitos_trabalhistas --situacao positiva

Cada comando aceita --saida caminho/arquivo.pdf pra escolher onde salvar
(por padrao salva na pasta atual). Rode --help em qualquer subcomando pra
ver todas as opcoes (nome, cpf, numero de matricula, etc. -- tudo pode
ser customizado, ou deixado no valor de exemplo padrao).

USO (como biblioteca, pra gerar varios de uma vez num script proprio):
    from gerar_documentos_teste import gerar_rg, gerar_matricula, gerar_certidao
    gerar_rg("saida/rg_fulano.pdf", nome="Fulano de Tal", cpf="123.456.789-00")
"""
import argparse
import random
import textwrap

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm


AVISO = "DOCUMENTO FICTÍCIO — SEM VALIDADE LEGAL — USO EXCLUSIVO PARA TESTES DE SOFTWARE"


def _cabecalho_aviso(c, largura, altura):
    """Desenha o aviso de documento ficticio no topo E como marca d'agua
    diagonal no meio da pagina -- redundante de proposito, pra ser
    impossivel de nao notar (inclusive se alguem cortar/recortar so' uma
    parte da imagem)."""
    c.setFillColorRGB(0.75, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 9)
    linhas = textwrap.wrap(AVISO, 70)
    y = altura - 1.2 * cm
    for linha in linhas:
        c.drawCentredString(largura / 2, y, linha)
        y -= 0.35 * cm

    c.saveState()
    c.setFillColorRGB(0.85, 0.85, 0.85)
    c.setFont("Helvetica-Bold", 40)
    c.translate(largura / 2, altura / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "FICTÍCIO — TESTE")
    c.restoreState()
    c.setFillColorRGB(0, 0, 0)


def _rodape_aviso(c, largura):
    c.setFillColorRGB(0.75, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(largura / 2, 1 * cm, AVISO)
    c.setFillColorRGB(0, 0, 0)


def gerar_rg(saida: str, nome: str = "José Fictício da Silva Teste",
             cpf: str = None, rg: str = None, estado_civil: str = "solteiro",
             profissao: str = "Analista de Sistemas", nacionalidade: str = "brasileiro",
             endereco: str = "Rua dos Testes, 123 — Bairro Exemplo — Curitiba/PR",
             orgao_expedidor: str = "SSP/PR") -> str:
    """Gera um 'documento de identificação' ficticio (RG+CPF juntos num
    layout simples) -- serve pra testar o schema 'pessoa' da extracao."""
    cpf = cpf or _cpf_falso()
    rg = rg or str(random.randint(10_000_000, 99_999_999)) + "-" + str(random.randint(0, 9))

    c = canvas.Canvas(saida, pagesize=A4)
    largura, altura = A4
    _cabecalho_aviso(c, largura, altura)

    y = altura - 4 * cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, y, "CARTEIRA DE IDENTIDADE (documento fictício de teste)")
    y -= 1 * cm

    campos = [
        ("Nome", nome),
        ("Nacionalidade", nacionalidade),
        ("Estado civil", estado_civil),
        ("Profissão", profissao),
        ("RG nº", rg),
        ("Órgão expedidor", orgao_expedidor),
        ("CPF", cpf),
        ("Endereço", endereco),
    ]
    c.setFont("Helvetica", 11)
    for rotulo, valor in campos:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2 * cm, y, f"{rotulo}:")
        c.setFont("Helvetica", 11)
        c.drawString(6 * cm, y, str(valor))
        y -= 0.8 * cm

    _rodape_aviso(c, largura)
    c.save()
    return saida


def _cpf_falso() -> str:
    """CPF com formato valido mas numero claramente de teste (nunca
    corresponde a CPF real emitido -- usa a faixa reservada pra
    exemplos/documentacao, mesmo padrao que a Receita Federal recomenda
    pra CPFs de exemplo em manuais)."""
    n = random.randint(100, 999)
    return f"{n}.{random.randint(100,999)}.{random.randint(100,999)}-{random.randint(10,99)}"


def gerar_matricula(saida: str, matricula_num: str = None, proprietario: str = "Maria Fictícia de Teste",
                     cpf_proprietario: str = None, descricao_imovel: str = None,
                     endereco: str = "Rua Exemplo, 456 — Curitiba/PR",
                     cartorio: str = "1º Cartório de Registro de Imóveis Fictício de Curitiba",
                     circunscricao: str = "1ª",
                     onus: str = None) -> str:
    """Gera uma 'certidao de matricula' ficticia, no formato narrativo de
    registros (R-) e averbacoes (Av-), igual matricula de verdade -- so'
    que com cartorio, numero e nomes inventados. Passe onus=None pra
    matricula limpa (sem gravame vigente), ou onus='alienacao_fiduciaria'
    /'hipoteca'/'usufruto' pra incluir um onus vigente de teste (sem
    baixa averbada), servindo pra testar a extracao de onus_vigente."""
    matricula_num = matricula_num or str(random.randint(10000, 99999))
    cpf_proprietario = cpf_proprietario or _cpf_falso()
    descricao_imovel = descricao_imovel or (
        "Apartamento nº 12, tipo AP-2-50, do 3º pavimento, do Bloco 02, do "
        "'Condomínio Fictício de Teste', com área construída de 55,30 m², "
        "fração ideal do solo de 0,03120"
    )

    c = canvas.Canvas(saida, pagesize=A4)
    largura, altura = A4
    _cabecalho_aviso(c, largura, altura)

    y = altura - 4.2 * cm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2 * cm, y, f"MATRÍCULA Nº {matricula_num} (documento fictício de teste)")
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"{circunscricao} Circunscrição — {cartorio}")
    y -= 1 * cm

    def paragrafo(texto, negrito_inicio=None):
        nonlocal y
        c.setFont("Helvetica", 9.5)
        for linha in textwrap.wrap(texto, 95):
            c.drawString(2 * cm, y, linha)
            y -= 0.42 * cm
        y -= 0.3 * cm

    paragrafo(
        f"IMÓVEL - {descricao_imovel}, situado à {endereco}."
    )
    paragrafo(
        f"PROPRIETÁRIA - {proprietario}, CPF nº {cpf_proprietario}, estado civil solteira, "
        f"residente e domiciliada no próprio imóvel."
    )
    paragrafo(
        "TÍTULO AQUISITIVO - Matrícula de origem 11111 deste Ofício."
    )
    paragrafo(
        "R.1/" + matricula_num + " - Protocolo 900.001, de 10/01/2020 - Consoante Escritura Pública "
        "de Compra e Venda, lavrada às fls. 10, do Livro nº 500-N, neste Tabelionato Fictício, em "
        "05/01/2020, o(a) proprietário(a) anterior vendeu o imóvel objeto da presente matrícula a " +
        proprietario + ", CPF nº " + cpf_proprietario + ", pelo preço de R$ 300.000,00. Dou fé. "
        "Curitiba, 10 de janeiro de 2020. (a) OFICIAL DO REGISTRO (fictício)."
    )

    if onus:
        mapa_onus = {
            "alienacao_fiduciaria": (
                "R.2/" + matricula_num + " - Protocolo 900.002, de 15/03/2022 - Consoante Contrato "
                "de Venda e Compra de Imóvel, Mútuo e Alienação Fiduciária em Garantia, firmado em "
                "Curitiba-PR, em 10/03/2022, " + proprietario + " ALIENOU FIDUCIARIAMENTE o imóvel "
                "objeto da presente matrícula em favor do Banco Fictício de Testes S.A., para garantia "
                "de financiamento no valor de R$ 113.600,00. Dou fé. Curitiba, 15 de março de 2022. "
                "(a) OFICIAL DO REGISTRO (fictício)."
            ),
            "hipoteca": (
                "AV.2/" + matricula_num + " - Protocolo 900.003, de 20/05/2021 - Consta hipoteca em "
                "primeiro grau constituída em favor do Banco Fictício de Testes S.A., para garantia de "
                "financiamento no valor de R$ 80.000,00. Dou fé. Curitiba, 20 de maio de 2021. "
                "(a) OFICIAL DO REGISTRO (fictício)."
            ),
            "usufruto": (
                "R.2/" + matricula_num + " - Protocolo 900.004, de 01/02/2023 - " + proprietario + " "
                "reservou para si o usufruto vitalício sobre o imóvel objeto da presente matrícula, "
                "na forma do artigo 1.390 do Código Civil. Dou fé. Curitiba, 1 de fevereiro de 2023. "
                "(a) OFICIAL DO REGISTRO (fictício)."
            ),
        }
        paragrafo(mapa_onus.get(onus, mapa_onus["alienacao_fiduciaria"]))
    else:
        paragrafo(
            "Não constam ônus, gravames ou restrições vigentes sobre o imóvel objeto da presente "
            "matrícula até a presente data (documento fictício de teste)."
        )

    _rodape_aviso(c, largura)
    c.save()
    return saida


TIPOS_CERTIDAO_VALIDOS = [
    "debitos_trabalhistas", "feitos_1_distribuidor", "feitos_2_distribuidor",
    "feitos_trt", "feitos_trf", "tributos_federais", "tributos_estaduais",
    "feitos_comarca_diferente",
]

NOMES_LEGIVEIS_CERTIDAO = {
    "debitos_trabalhistas": "CERTIDÃO DE DÉBITOS TRABALHISTAS",
    "feitos_1_distribuidor": "CERTIDÃO DE FEITOS AJUIZADOS — 1º DISTRIBUIDOR",
    "feitos_2_distribuidor": "CERTIDÃO DE FEITOS AJUIZADOS — 2º DISTRIBUIDOR",
    "feitos_trt": "CERTIDÃO DE FEITOS AJUIZADOS — TRT",
    "feitos_trf": "CERTIDÃO DE FEITOS AJUIZADOS — TRF",
    "tributos_federais": "CERTIDÃO DE TRIBUTOS FEDERAIS",
    "tributos_estaduais": "CERTIDÃO DE TRIBUTOS ESTADUAIS",
    "feitos_comarca_diferente": "CERTIDÃO DE FEITOS AJUIZADOS — COMARCA DIFERENTE",
}

# Tipos que costumam ter numero proprio (tributos); os de distribuidor/feitos
# geralmente nao tem -- so' pra deixar o documento de teste mais realista,
# nao afeta a extracao (a IA decide olhando o documento, nao o nome do tipo)
TIPOS_COM_NUMERO = {"tributos_federais", "tributos_estaduais"}


def gerar_certidao(saida: str, tipo: str = "tributos_federais", situacao: str = "negativa",
                    nome_pessoa: str = "José Fictício da Silva Teste", cpf_pessoa: str = None,
                    data_emissao: str = "01/06/2026", data_validade: str = "01/12/2026",
                    numero: str = None) -> str:
    """Gera uma certidao ficticia de um dos 8 tipos usados no sistema.
    'situacao' pode ser 'negativa', 'positiva', ou 'positiva com efeito de negativa'."""
    if tipo not in TIPOS_CERTIDAO_VALIDOS:
        raise ValueError(f"tipo deve ser um de: {TIPOS_CERTIDAO_VALIDOS}")
    cpf_pessoa = cpf_pessoa or _cpf_falso()
    tem_numero = tipo in TIPOS_COM_NUMERO
    if tem_numero and numero is None:
        numero = str(random.randint(100000, 999999))

    c = canvas.Canvas(saida, pagesize=A4)
    largura, altura = A4
    _cabecalho_aviso(c, largura, altura)

    y = altura - 4.5 * cm
    c.setFont("Helvetica-Bold", 13)
    for linha in textwrap.wrap(NOMES_LEGIVEIS_CERTIDAO[tipo] + " (documento fictício de teste)", 55):
        c.drawCentredString(largura / 2, y, linha)
        y -= 0.6 * cm
    y -= 0.6 * cm

    c.setFont("Helvetica", 10.5)
    linhas = [
        f"Nome: {nome_pessoa}",
        f"CPF: {cpf_pessoa}",
    ]
    if tem_numero:
        linhas.append(f"Certidão nº: {numero}")
    linhas.append(f"Data de emissão: {data_emissao}")
    linhas.append(f"Válida até: {data_validade}")
    linhas.append("")
    if situacao == "negativa":
        linhas.append("Certifica-se que, na data de emissão desta certidão, NADA CONSTA em nome")
        linhas.append("da pessoa acima qualificada nos registros consultados.")
    elif situacao == "positiva com efeito de negativa":
        linhas.append("Certifica-se que CONSTAM débitos em nome da pessoa acima qualificada,")
        linhas.append("porém com exigibilidade suspensa, razão pela qual esta certidão é expedida")
        linhas.append("com EFEITOS DE CERTIDÃO NEGATIVA.")
    else:
        linhas.append("Certifica-se que CONSTAM pendências em nome da pessoa acima qualificada")
        linhas.append("nos registros consultados (documento fictício de teste — certidão POSITIVA).")

    for linha in linhas:
        c.drawString(2 * cm, y, linha)
        y -= 0.55 * cm

    _rodape_aviso(c, largura)
    c.save()
    return saida


def _cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)

    p_rg = sub.add_parser("rg", help="Gera documento de identificação fictício (schema 'pessoa')")
    p_rg.add_argument("--saida", default="rg_teste.pdf")
    p_rg.add_argument("--nome", default="José Fictício da Silva Teste")
    p_rg.add_argument("--cpf")
    p_rg.add_argument("--estado-civil", default="solteiro")

    p_mat = sub.add_parser("matricula", help="Gera matrícula de imóvel fictícia")
    p_mat.add_argument("--saida", default="matricula_teste.pdf")
    p_mat.add_argument("--proprietario", default="Maria Fictícia de Teste")
    p_mat.add_argument("--onus", choices=["alienacao_fiduciaria", "hipoteca", "usufruto"], default=None)
    p_mat.add_argument("--sem-onus", action="store_true")

    p_cert = sub.add_parser("certidao", help="Gera certidão fictícia de um dos 8 tipos usados no sistema")
    p_cert.add_argument("--saida", default="certidao_teste.pdf")
    p_cert.add_argument("--tipo", choices=TIPOS_CERTIDAO_VALIDOS, default="tributos_federais")
    p_cert.add_argument("--situacao", choices=["negativa", "positiva", "positiva com efeito de negativa"], default="negativa")
    p_cert.add_argument("--nome", default="José Fictício da Silva Teste")

    args = ap.parse_args()

    if args.comando == "rg":
        caminho = gerar_rg(args.saida, nome=args.nome, cpf=args.cpf, estado_civil=args.estado_civil)
    elif args.comando == "matricula":
        onus = None if args.sem_onus else args.onus
        caminho = gerar_matricula(args.saida, proprietario=args.proprietario, onus=onus)
    elif args.comando == "certidao":
        caminho = gerar_certidao(args.saida, tipo=args.tipo, situacao=args.situacao, nome_pessoa=args.nome)

    print(f"Gerado: {caminho}")


if __name__ == "__main__":
    _cli()
