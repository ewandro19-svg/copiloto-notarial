# Deploy do Copiloto Notarial (versão FastAPI)

A arquitetura mudou desde o último guia: agora é **uma API (FastAPI)** que
serve o próprio site junto — não é mais Streamlit. Isso significa que o
Streamlit Community Cloud **não serve mais** (ele só hospeda apps
Streamlit). O equivalente pra esse tipo de aplicação é a **Render**.

Continua tudo por clique e arrastar arquivo — sem terminal, sem git.

**Esse guia já é pra uma beta com pessoas de fora testando** (não mais
só demonstração) — por isso usa o plano **Starter** (pago, ~$7/mês) com
**disco persistente**, em vez do plano Free. A diferença prática: o
serviço não "dorme" mais entre acessos, e os logins/histórico não somem
a cada redeploy. Ver seção "Por que não ficar no Free" no final.

## 1. GitHub — se você já tem o repositório de antes
Se já subiu o projeto antigo pro GitHub, é só **atualizar os arquivos**
(mesmo repositório, mesmo passo de "editar arquivo" que já fizemos com o
`app.py`). Se for começar do zero, repete os passos 1-3 do guia anterior
(criar conta, criar repositório, arrastar a pasta `minuta-ia` inteira).

**Atenção**: essa versão tem uma pasta nova, `backend/`, e uma pasta
`frontend/` — confirma que as duas subiram junto com o resto.

## 2. Criar conta na Render
🔗 **[render.com](https://render.com)**
- Clica em "Get Started" ou "Sign Up"
- Escolhe "Sign up with GitHub" (conecta os dois automaticamente, igual
  fizemos com o Streamlit)
- O plano Starter pede cartão de crédito (o Free não pedia)

## 3. Criar o serviço
- No painel da Render, clica em **"New +"** → **"Web Service"**
- Escolhe o repositório `copiloto-notarial`
- Preenche:
  - **Name**: `copiloto-notarial` (ou o que preferir)
  - **Region**: qualquer uma (Oregon serve bem)
  - **Branch**: `main`
  - **Root Directory**: deixa em branco (a menos que o repositório tenha
    a pasta `minuta-ia` como subpasta — nesse caso, coloca `minuta-ia`
    aqui)
  - **Runtime**: `Python 3`
  - **Build Command**: `pip install -r requirements.txt`
  - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
  - **Instance Type**: **Starter** (~$7/mês — não fica mais no Free pra
    uma beta com gente de fora testando, ver explicação no final)

## 4. Adicionar o disco persistente (novo neste guia)
Isso é o que garante que login e histórico não sumam a cada redeploy —
sem isso, o Starter sozinho tem o MESMO problema de reset que o Free tinha.
- Ainda na tela de criação do serviço (ou depois, em "Disks"), procura
  **"Add Disk"**
- **Name**: `dados-persistentes` (ou qualquer nome)
- **Mount Path**: `/var/data` (o código já está preparado pra usar esse
  caminho — ver variável `DADOS_DIR` no passo 5, sem ela o disco fica
  conectado mas vazio)
- **Size**: 1 GB já sobra bastante (é só texto — usuários, histórico de
  metadados de minutas, nada de PDF fica salvo)
- Custo do disco: alguns centavos de dólar por mês (bem menos que o
  próprio Starter)

## 5. Adicionar a chave da API e o caminho do disco
- Na mesma tela, procura **"Environment Variables"**
- Clica em "Add Environment Variable" e adiciona as duas:
  - Key: `ANTHROPIC_API_KEY` — Value: sua chave de verdade (a mesma de
    antes, ou uma nova se você apagou a antiga por segurança)
  - Key: `DADOS_DIR` — Value: `/var/data` (esse é o que faz o login e o
    histórico realmente irem pro disco persistente do passo 4 — sem essa
    variável, o disco fica lá conectado mas vazio, e os bancos continuam
    se perdendo a cada redeploy do mesmo jeito que no Free)

## 6. Criar o serviço
- Clica em **"Create Web Service"**
- A Render builda e sobe sozinha — leva de 2 a 5 minutos na primeira vez
- Quando terminar, aparece um link tipo `https://copiloto-notarial.onrender.com`

## 7. Entrar pela primeira vez (login mudou desde o último guia)
**Não existe mais "Primeiro acesso? Criar conta"** — esse autocadastro
público foi desativado de propósito (só admin cadastra usuário agora,
pela própria tela de Configurações → Usuários). O sistema já sobe com
um login pronto na primeira vez que o banco estiver vazio:

- **Usuário**: `ewandro.teste`
- **Senha**: `teste12345`

Entra com isso e — **primeira coisa a fazer** — troca a senha ou cria
seu login de verdade em Configurações → Usuários (esse login já nasce
Administrador, então pode cadastrar os outros testers por ali).

## Convidando os testers
Como não tem mais autocadastro, você mesmo cria o login de cada tester
em Configurações → Usuários (nome, login, senha) e passa a senha pra
pessoa por fora (WhatsApp, etc.) — ela não escolhe a própria senha na
primeira vez, você define.

## Por que não ficar no Free pra essa fase
- **Free "dorme"** depois de 15 min sem uso — pra demonstração pontual
  não incomodava, mas pra alguém testar no dia a dia é ruim (30-60s de
  espera toda vez que reabre)
- **Free não tem disco persistente** — login e histórico resetam a
  qualquer redeploy, o que quebra a experiência de teste continuado
- Com 1-3 testers, o custo total (Starter + disco) fica em torno de
  **R$ 40-45/mês** — separado do custo de API (Claude), que é por uso

## Se algo der errado
Na Render, os erros aparecem em **"Logs"** (aba lateral do seu serviço).
Copia e cola aqui a mensagem de erro que aparecer.
