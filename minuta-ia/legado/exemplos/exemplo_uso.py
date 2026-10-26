"""
Testa a logica condicional do template com 3 cenarios diferentes:

  1. A vista, vendedor unico, sem outorga, sem usufruto (o caso simples)
  2. Financiado, com outorga do conjuge (regime exige)
  3. A vista, DOIS vendedores (herdeiros), COM usufruto reservado

Em uso real, esses dicionarios vem do extrair_dados.py rodando sobre os
documentos de cada parte -- aqui estao fixos pra testar a logica sem
depender de documento real.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from gerar_minuta import gerar

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "minuta_compra_venda.docx")
SAIDA_DIR = os.path.dirname(__file__)

cartorio = {
    "nome": "1º Tabelionato de Notas de Catanduva",
    "municipio": "Catanduva",
    "uf": "SP",
    "endereco": "Rua XV de Novembro, 800, Centro",
}
escrevente = {"nome": "Fulano de Tal", "cargo": "Escrevente Autorizado"}

imovel_base = {
    "descricao": "apartamento residencial",
    "endereco": "Rua das Palmeiras, 250, apto 32, Vila Nova, Catanduva/SP",
    "matricula": "45.678",
    "oficio_registro": "1º Ofício de Registro de Imóveis de Catanduva/SP",
    "area": "85,40 m²",
    "inscricao_iptu": "12.345.6789.001",
    "titulo_aquisitivo": "compra e venda registrada sob R-3 da matrícula",
}

certidoes = {
    "lista": (
        "Certidão de Matrícula atualizada, Certidão Negativa de Ônus Reais, "
        "Certidão Negativa de Débitos Municipais (IPTU), Certidões pessoais "
        "das partes (cível, protesto, trabalhista e federal)"
    )
}

# ============================================================================
# CENARIO 1 — a vista, vendedor unico, regime que NAO exige outorga
# ============================================================================
cenario_1 = {
    "vendedores": [{
        "nome": "José Maria da Silva",
        "nacionalidade": "brasileiro",
        "estado_civil": "solteiro",
        "profissao": "engenheiro civil",
        "rg": "12.345.678-9",
        "cpf": "123.456.789-00",
        "endereco": "Rua das Flores, 100, apto 21, Centro, Catanduva/SP",
        "conjuge": None,
        "exige_outorga": False,
    }],
    "compradores": [{
        "nome": "Ana Paula Oliveira",
        "nacionalidade": "brasileira",
        "estado_civil": "solteira",
        "profissao": "médica",
        "rg": "98.765.432-1",
        "cpf": "987.654.321-00",
        "endereco": "Avenida Brasil, 500, Jardim Primavera, Catanduva/SP",
    }],
    "imovel": imovel_base,
    "negocio": {
        "forma_pagamento": "a_vista",
        "valor_extenso": "quatrocentos e cinquenta mil reais",
        "valor_numerico": "R$ 450.000,00",
        "itbi_valor": "R$ 13.500,00",
        "itbi_guia": "2026/00123456",
    },
    "usufruto": None,
    "certidoes": certidoes,
    "cartorio": cartorio,
    "escrevente": escrevente,
    "data_ato_extenso": "vinte dias do mês de agosto do ano de dois mil e vinte e seis",
}

# ============================================================================
# CENARIO 2 — financiado, vendedor casado em comunhao parcial (exige outorga)
# ============================================================================
cenario_2 = {
    "vendedores": [{
        "nome": "Carlos Eduardo Souza",
        "nacionalidade": "brasileiro",
        "estado_civil": "casado sob o regime de comunhão parcial de bens",
        "profissao": "comerciante",
        "rg": "11.222.333-4",
        "cpf": "111.222.333-44",
        "endereco": "Rua Sete de Setembro, 45, Catanduva/SP",
        "conjuge": {
            "nome": "Marta Souza",
            "nacionalidade": "brasileira",
            "profissao": "professora",
            "rg": "22.333.444-5",
            "cpf": "222.333.444-55",
        },
        "exige_outorga": True,
    }],
    "compradores": [{
        "nome": "Roberto Lima",
        "nacionalidade": "brasileiro",
        "estado_civil": "solteiro",
        "profissao": "autônomo",
        "rg": "33.444.555-6",
        "cpf": "333.444.555-66",
        "endereco": "Rua Bahia, 12, Catanduva/SP",
    }],
    "imovel": imovel_base,
    "negocio": {
        "forma_pagamento": "financiado",
        "valor_extenso": "quinhentos mil reais",
        "valor_numerico": "R$ 500.000,00",
        "valor_entrada": "R$ 100.000,00",
        "valor_financiado": "R$ 400.000,00",
        "financiamento": {
            "instituicao": "Banco XYZ S.A.",
            "contrato_numero": "2026-998877",
        },
        "itbi_valor": "R$ 15.000,00",
        "itbi_guia": "2026/00223344",
    },
    "usufruto": None,
    "certidoes": certidoes,
    "cartorio": cartorio,
    "escrevente": escrevente,
    "data_ato_extenso": "vinte dias do mês de agosto do ano de dois mil e vinte e seis",
}

# ============================================================================
# CENARIO 3 — dois vendedores (herdeiros), a vista, COM usufruto reservado
# ============================================================================
cenario_3 = {
    "vendedores": [
        {
            "nome": "Pedro Almeida",
            "nacionalidade": "brasileiro",
            "estado_civil": "viúvo",
            "profissao": "aposentado",
            "rg": "44.555.666-7",
            "cpf": "444.555.666-77",
            "endereco": "Rua Minas Gerais, 88, Catanduva/SP",
            "conjuge": None,
            "exige_outorga": False,
        },
        {
            "nome": "Juliana Almeida",
            "nacionalidade": "brasileira",
            "estado_civil": "solteira",
            "profissao": "arquiteta",
            "rg": "55.666.777-8",
            "cpf": "555.666.777-88",
            "endereco": "Rua Minas Gerais, 88, Catanduva/SP",
            "conjuge": None,
            "exige_outorga": False,
        },
    ],
    "compradores": [{
        "nome": "Fernando Costa",
        "nacionalidade": "brasileiro",
        "estado_civil": "casado sob separação total de bens",
        "profissao": "empresário",
        "rg": "66.777.888-9",
        "cpf": "666.777.888-99",
        "endereco": "Avenida Paulista, 1000, São Paulo/SP",
    }],
    "imovel": imovel_base,
    "negocio": {
        "forma_pagamento": "a_vista",
        "valor_extenso": "seiscentos mil reais",
        "valor_numerico": "R$ 600.000,00",
        "itbi_valor": "R$ 18.000,00",
        "itbi_guia": "2026/00334455",
    },
    "usufruto": {"beneficiario": "Pedro Almeida"},
    "certidoes": certidoes,
    "cartorio": cartorio,
    "escrevente": escrevente,
    "data_ato_extenso": "vinte dias do mês de agosto do ano de dois mil e vinte e seis",
}

if __name__ == "__main__":
    for nome, ctx in [
        ("cenario_1_a_vista_simples", cenario_1),
        ("cenario_2_financiado_outorga", cenario_2),
        ("cenario_3_multiplas_partes_usufruto", cenario_3),
    ]:
        saida = os.path.join(SAIDA_DIR, f"minuta_{nome}.docx")
        gerar(ctx, TEMPLATE, saida)
        print(f"Gerado: {saida}")
