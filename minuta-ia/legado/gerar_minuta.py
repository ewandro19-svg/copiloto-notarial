"""
Pega os dados ja extraidos (de vendedor, comprador, imovel, cartorio, negocio)
e preenche o template da minuta, gerando o docx final pronto pra conferencia.

USO (ve exemplo_uso.py pra um fluxo completo ponta a ponta):
    from gerar_minuta import gerar
    gerar(contexto_dict, "templates/minuta_compra_venda.docx", "saida/minuta_001.docx")
"""
from docxtpl import DocxTemplate


def gerar(contexto: dict, template_path: str, saida_path: str):
    doc = DocxTemplate(template_path)
    doc.render(contexto)
    doc.save(saida_path)
    return saida_path
