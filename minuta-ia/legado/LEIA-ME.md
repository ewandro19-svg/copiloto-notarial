# Legado

Esses arquivos eram do **primeiro protótipo**, feito em Streamlit, antes da
gente migrar pra uma API (FastAPI) + o mockup visual conectado de verdade.

- `app.py` — o app Streamlit completo, funcional, mas com o visual padrão
  do Streamlit (não o visual customizado do produto).
- `gerar_minuta.py` — gerava o docx usando um template `.docx` fixo com
  `docxtpl`. Foi substituído pelo motor de fragmentação por item
  (`scripts/motor_minuta.py`), que monta o texto dinamicamente e usa
  `python-docx` puro pra escrever o arquivo final.
- `criar_template.py` — script que gerava esse template `.docx` fixo.
- `exemplos/` — exemplos de uso do fluxo antigo.

Nada aqui é usado pela aplicação atual (`backend/main.py` +
`frontend/index.html`). Ficou guardado só como histórico/referência.
