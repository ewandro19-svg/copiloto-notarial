# Copiloto Notarial — protótipo

"Você decide. Ele digita."

Protótipo funcional: extrai dados de documentos (RG, CPF, matrícula) via IA e gera
a minuta de escritura de compra e venda já preenchida, pronta pra conferência —
já com lógica condicional pras variações mais comuns de uma compra e venda.

## O que já funciona (testado com 3 cenários)

- `templates/minuta_compra_venda.docx` — modelo com marcadores `{{ }}` e blocos
  condicionais `{% if %}`/`{% for %}`, no formato Jinja2 (via `docxtpl`).
  **Troque os textos marcados com `[SUBSTITUIR]` pela redação real aprovada no
  seu tabelionato antes de usar com ato de verdade** — são placeholders
  genéricos só pra provar a lógica.
- **Lógica condicional já implementada e testada:**
  - Vendedores e compradores em **lista** (funciona pra 1 parte ou várias —
    ex: herdeiros vendendo em conjunto).
  - **Outorga do cônjuge** — só aparece se `exige_outorga: true` no vendedor.
  - **Forma de pagamento**: bloco de cláusula diferente pra `a_vista` vs
    `financiado` (com dados de instituição financeira e contrato).
  - **Usufruto reservado** — bloco opcional, só aparece se informado.
- `scripts/extrair_dados.py` — manda um documento (imagem ou PDF) pra API da
  Anthropic e recebe de volta um JSON com os campos que a minuta precisa.
- `scripts/gerar_minuta.py` — pega esse JSON (de vendedor, comprador, imóvel
  etc.) e preenche o template, gerando o `.docx` final.
- `exemplos/exemplo_uso.py` — gera **3 cenários de teste**: (1) à vista simples,
  (2) financiado com outorga do cônjuge, (3) dois vendedores + usufruto. Rodei
  os três aqui e conferi visualmente que cada bloco condicional aparece só
  quando deveria.

## Como rodar a interface web (com login)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sua-chave-aqui"

# 1. Criar seu usuário (e o de quem for testar) -- sem auto-cadastro, so voce cria
python3 scripts/criar_usuario.py
# vai perguntar username, senha (min. 8 caracteres), nome e cartório

# 2. Subir o app
streamlit run app.py
# abre em http://localhost:8501 -- pede login, depois upload de RG/CPF/matricula,
# mostra os dados extraidos pra voce conferir/corrigir, e gera a minuta pra baixar
```

Autenticação real: senha nunca fica em texto puro (hash com `bcrypt`), fica
guardada em `usuarios.db` (SQLite local). **Isso não é um sistema enterprise**
(sem recuperação de senha por e-mail, sem 2FA) — mas é login de verdade, não
gambiarra. Pra dar acesso a alguém testar, você roda `criar_usuario.py` de novo
com o username/senha da pessoa.

**Se for testar com alguém fora da sua rede/máquina:** rodar `streamlit run`
só deixa acessível na sua própria máquina por padrão. Pra outra pessoa acessar
remotamente, ou você expõe a porta (cuidado, dado sensível trafegando) ou usa
algo como `streamlit run app.py` + túnel temporário (ex: ngrok) só durante o
teste, nunca deixando aberto publicamente sem HTTPS.

## Como rodar por linha de comando (sem interface, pra testes rápidos)

```bash
# 1. Extrair dados de um documento real
python3 scripts/extrair_dados.py caminho/rg_vendedor.jpg --tipo pessoa > vendedor.json
python3 scripts/extrair_dados.py caminho/rg_comprador.jpg --tipo pessoa > comprador.json
python3 scripts/extrair_dados.py caminho/matricula.pdf --tipo imovel > imovel.json

# 2. Rodar os 3 cenarios de teste (dados ficticios) e ver a logica condicional funcionando
python3 exemplos/exemplo_uso.py
# gera: minuta_cenario_1_a_vista_simples.docx
#       minuta_cenario_2_financiado_outorga.docx
#       minuta_cenario_3_multiplas_partes_usufruto.docx
```

## Próximos passos sugeridos (nessa ordem)

1. **Trocar os `[SUBSTITUIR]` pelo texto real aprovado no seu tabelionato**
   (outorga uxória, cláusula de alienação fiduciária, reserva de usufruto).
   Isso é trabalho jurídico seu, não técnico — a lógica de quando cada bloco
   aparece já está pronta, só falta o conteúdo de cada um.
2. **Trocar o restante do template genérico** pela redação padrão real do seu
   tabelionato (o miolo da escritura, fora dos blocos condicionais).
3. **Montar uma tela simples de upload** (ex: Streamlit, ~30 linhas) pra não
   precisar rodar comando de terminal toda vez — sobe o RG, CPF e matrícula,
   clica "gerar minuta", baixa o docx.
4. **Adicionar mais tipos de ato** (doação, inventário) — cada um precisa de
   um template novo e, possivelmente, um schema de extração novo em
   `SCHEMAS` no `extrair_dados.py`.
5. **Testar com casos reais antigos e já finalizados** do seu cartório (dado
   anonimizado ou já público) e comparar o texto gerado com o que foi
   lavrado de verdade — isso mede se a IA está extraindo certo antes de
   confiar nela com caso novo.
6. Certidão automática fica pra depois, como combinado.

## Cuidado com dado sensível

Este protótipo manda o conteúdo do documento (RG, CPF, endereço, dados
patrimoniais) pra API de um provedor de IA externo. Antes de usar com
documento real de cliente:

- Confira a política de retenção/uso pra treinamento da API que você escolher.
- Considere ambiente Zero Data Retention, se disponível no seu plano.
- Verifique se isso está coberto no seu tratamento de dados sob a LGPD (base
  legal, informação ao titular, etc.) — vale conversa com quem cuida disso no
  seu cartório.
