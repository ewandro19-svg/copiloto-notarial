"""
Extrai dados estruturados de documentos (RG, CPF, certidao de matricula, etc.)
usando a API da Anthropic (Claude), com output multimodal (imagem/PDF -> JSON).

USO:
    python3 extrair_dados.py caminho/rg_vendedor.jpg --papel vendedor
    python3 extrair_dados.py caminho/matricula.pdf --papel imovel

Requer variavel de ambiente ANTHROPIC_API_KEY.

IMPORTANTE (dado sensivel): este script envia o documento pra API de terceiro.
Confira a politica de retencao/treinamento de dados do provedor de IA que voce
escolher antes de usar com documento real de cliente. Considere um ambiente
com Zero Data Retention se disponivel.
"""
import sys
import json
import base64
import argparse
import os
import time

from extracao_log import registrar_extracao

# Timeout maximo (em segundos) por chamada de extracao. Sem isso, o SDK
# usa um timeout padrao muito longo (~10 minutos) -- se a rede engasgar
# ou a API demorar, o usuario fica vendo "Lendo documentos..." parado
# por ate 10 min, sem nenhum aviso de erro. Com o timeout explicito, o
# sistema desiste rapido e mostra uma mensagem clara em vez de travar.
# Matricula pode legitimamente demorar mais (documento maior, mais
# raciocinio), entao tem um teto proprio, mais folgado.
TIMEOUT_PADRAO_SEGUNDOS = 60
TIMEOUT_IMOVEL_SEGUNDOS = 120
import anthropic

# Schemas esperados por tipo de documento -- isso guia o modelo a devolver
# exatamente os campos que a minuta precisa, nada a mais, nada a menos.
SCHEMAS = {
    "cnh": {
        "descricao": "Dados de uma Carteira Nacional de Habilitacao (CNH)",
        "campos": {
            "numero": "numero de registro da CNH",
            "orgao_emissor": "orgao emissor, no formato 'DETRAN/UF' (ex: 'DETRAN/PR')",
            "data_expedicao": "data de expedicao/emissao desta CNH, formato DD/MM/AAAA",
            "nome": "nome completo do titular, pra conferencia cruzada com o RG",
            "cpf": "numero do CPF do titular, se constar na CNH, formatado 000.000.000-00",
        },
    },
    "pessoa": {
        "descricao": "Dados de uma pessoa fisica a partir de RG e/ou CPF",
        "campos": {
            "nome": "nome completo",
            "nacionalidade": "nacionalidade da pessoa, JA GENERIZADA conforme o sexo dela -- 'brasileiro' ou 'brasileira', nunca 'brasileiro(a)' com parenteses. Escolha uma forma so', baseado no que o documento indicar (nome, tratamento, ou outro sinal visivel).",
            "sexo": "sexo da pessoa, EXATAMENTE como consta no campo 'Sexo' ou 'Sex' do documento (RG/CNH quase sempre tem esse campo explicito) -- responda so' 'M' ou 'F', maiusculo, sem mais nada. Esse campo e' MUITO mais confiavel que tentar inferir pelo nome ou pela nacionalidade, porque vem impresso literalmente no documento -- SEMPRE preencha se o campo existir no documento, mesmo que a nacionalidade/genero ja' pareçam obvios por outro sinal. null so' se o documento genuinamente nao tiver esse campo (raro).",
            "naturalidade": "cidade e UF de nascimento, se constar no documento (ex: 'Curitiba/PR'). null se nao constar.",
            "data_nascimento": "data de nascimento da pessoa, formato DD/MM/AAAA, se constar no documento (RG e CNH costumam trazer). null se nao constar.",
            "estado_civil": "APENAS a palavra do estado civil, JA GENERIZADA conforme o sexo da pessoa -- 'solteiro' ou 'solteira', 'casado' ou 'casada', 'divorciado' ou 'divorciada', 'viuvo' ou 'viuva', 'separado' ou 'separada'. NUNCA escreva a forma com parenteses tipo 'casado(a)' -- escolha uma forma so', baseado no sexo da pessoa (mesmo sinal usado no campo 'sexo' e 'nacionalidade'). NAO inclua o regime de bens aqui -- isso vai no campo separado 'regime_bens'.",
            "regime_bens": "regime de bens, SO' se a pessoa for casada e isso constar no documento (ex: 'comunhao parcial de bens'). null se solteiro/viuvo/divorciado, ou se nao constar.",
            "profissao": "profissao declarada, SOMENTE se estiver EXPLICITAMENTE escrita no documento (ex: rotulo 'Profissao:' seguido do texto, ou uma CNH que declara categoria profissional). NUNCA infira, adivinhe ou presuma uma profissao a partir de idade, sexo, estado civil, ou qualquer estereotipo -- um RG ou CPF isolado quase nunca traz profissao, entao null e' o valor correto e esperado na maioria dos casos. Retorne null se o documento nao disser a profissao em nenhuma palavra.",
            "tipo_documento_identidade": "'RG' se o documento apresentado for a Cedula de Identidade, ou 'CNH' se for a Carteira Nacional de Habilitacao (a CNH tambem serve como documento de identidade e traz o numero do RG dentro dela)",
            "numero_cnh": "numero da CNH (Carteira Nacional de Habilitacao), SO' se tipo_documento_identidade for 'CNH'. null se for RG.",
            "orgao_cnh": "orgao emissor da CNH, formato 'DETRAN/UF' (ex: 'DETRAN/PR'), SO' se tipo_documento_identidade for 'CNH'. null se for RG.",
            "data_expedicao_cnh": "data de expedicao da CNH, formato DD/MM/AAAA, SO' se tipo_documento_identidade for 'CNH'. null se for RG.",
            "rg": "numero do RG (Cedula de Identidade) -- presente tanto se o documento apresentado for o proprio RG quanto se for a CNH (que sempre traz o numero do RG do titular impresso nela). ATENCAO: nos documentos de identidade em formato NOVO (a partir de ~2022), o RG e o CPF sao UNIFICADOS sob um unico campo, geralmente rotulado 'Registro Geral-CPF' ou 'Registro Geral-CPF / Personal Number' -- nesse formato, o numero do RG e' EXATAMENTE O MESMO numero do CPF (mesmo formato 000.000.000-00). Se o documento apresentar esse campo unificado, copie o MESMO numero tanto para 'rg' quanto para 'cpf' -- NUNCA deixe 'rg' vazio/null so' porque nao ha' um campo com rotulo 'RG' separado, quando esse campo unificado existir. Digito por digito com cuidado extra -- erros classicos de leitura sao confundir o digito 0 (zero) com a letra O, o digito 1 com a letra I, e o digito 5 com a letra S. Releia o numero antes de responder pra evitar essas trocas.",
            "orgao_expedidor": "orgao expedidor do RG, SEMPRE ABREVIADO no formato padrao 'SIGLA/UF' -- NUNCA o nome por extenso, mesmo que o documento imprima o nome completo. Exemplos de abreviacao: 'Secretaria de Seguranca Publica' -> 'SSP/UF'; 'Instituto de Identificacao do Parana' -> 'IIPR/PR'; 'Instituto Felix Pacheco' (RJ) -> 'IFP/RJ'; 'Instituto de Identificacao Ricardo Gumbleton Daunt' (SP) -> 'IIRGD/SP'; 'Policia Civil' -> 'PC/UF'; 'Policia Federal' -> 'PF'. Se o orgao do documento nao bater com nenhum exemplo conhecido, abrevie pra sigla mais curta e reconhecivel possivel (iniciais das palavras principais) + '/UF'.",
            "data_expedicao_rg": "data de expedicao do RG, formato DD/MM/AAAA, se constar. null se nao constar.",
            "cpf": "numero do CPF, formatado 000.000.000-00",
            "endereco": "endereco completo, se constar no documento",
        },
    },
    "imovel": {
        "descricao": "Dados de um imovel a partir da certidao de matricula",
        "campos": {
            "descricao": "descricao COMPLETA do imovel tal como consta na matricula -- tipo do imovel, metragem/area privativa, confrontacoes, numero de unidade/bloco/pavimento, vaga(s) de garagem, fracao ideal, e qualquer outro elemento descritivo que a matricula traga. NAO resuma pra so 'apartamento' ou 'casa, lote' -- reproduza a descricao completa. Sempre no PRESENTE -- ver instrucao especial abaixo sobre imovel em construcao",
            "endereco": "endereco completo do imovel, considerando a ultima averbacao de mudanca de numeracao/logradouro, se houver",
            "matricula": "APENAS o numero da matricula, nada mais -- nunca inclua o nome do oficio/serventia aqui (isso ja' vai em 'oficio_registro' separadamente). Ex: '13.092', nao '13.092 - 4o Oficio de Registro de Imoveis de Londrina'.",
            "oficio_registro": "nome do Oficio/Serventia de Registro de Imoveis -- se o documento mencionar o mesmo cartorio de duas formas diferentes (ex: nome no cabecalho E nome no rodape/selo de certificacao), sao a MESMA serventia -- escolha UMA forma (a mais completa) e nao concatene as duas.",
            "comarca": "comarca onde o imovel esta registrado",
            "circunscricao": "APENAS o numero/ordinal da circunscricao do Servico de Registro de Imoveis, JA' COM O 'ª' correto de ordinal feminino (ex: '8ª', NUNCA '8a' com a letra normal) e sem a palavra 'Circunscricao' junto (ex: '8ª', nao '8ª Circunscricao') -- relevante em comarcas com mais de um oficio",
            "area": "area total, se constar",
            "inscricao_iptu": "numero de inscricao municipal / contribuinte do IPTU, se constar em documentos do MUNICIPIO/prefeitura (carne de IPTU, certidao de tributos municipais) -- NAO confundir com 'indicacao_fiscal' (que e' um campo diferente, proprio da matricula do Registro de Imoveis).",
            "indicacao_fiscal": "numero da 'Indicacao Fiscal' EXATAMENTE como rotulado dentro da propria MATRICULA do imovel (procure o rotulo literal 'Indicacao Fiscal' ou 'Indicacao Fiscal da Unidade Especifica' no texto da matricula) -- e' um campo cadastral proprio do Registro de Imoveis, DIFERENTE do numero de inscricao municipal/contribuinte do IPTU (que fica em 'inscricao_iptu'). Se a matricula nao tiver esse rotulo explicito, retorne null -- nao use o numero de inscricao do IPTU como substituto.",
            "titulo_aquisitivo": "APENAS o codigo curto do registro pelo qual o atual proprietario adquiriu, sem descrever o tipo de negocio -- ex: 'R-3', NUNCA 'compra e venda registrada sob R-3' (o texto da minuta ja' complementa a frase em volta, o codigo sozinho basta)",
            "proprietario_atual": "nome do(s) proprietario(s) ATUAL(is) -- resultado final apos toda a cadeia de transmissoes, nao o primeiro nome que aparecer",
            "proprietarios_atuais_documento": "CPF ou CNPJ de cada proprietario atual, se constar na matricula (formato 'Nome: documento', um por linha/item se houver mais de um)",
            "proprietarios_atuais_estado_civil": "estado civil e regime de bens de cada proprietario atual, como consta no ultimo registro que os qualifica (util pra saber se exige outorga do conjuge)",
            "proprietarios_atuais_percentual": "percentual/fracao que cada proprietario atual detem do imovel, SE isso constar EXPLICITAMENTE na matricula (formato 'Nome: XX%', um por linha/item). Se a matricula nao deixar claro o percentual de cada um (ex: so' diz 'em comum' sem especificar fracao), retorne null -- NAO assuma divisao igual entre eles.",
            "sugestao_participacao_conjuge": "lista de sugestoes, uma por proprietario CASADO, sobre se o conjuge dele(a) provavelmente precisa assinar como vendedor(a)/outorgante ou dar anuencia, baseado no regime de bens (ex: comunhao parcial/universal costumam exigir participacao do conjuge, art. 1.647 CC; separacao total geralmente dispensa). SEMPRE deixe claro que e' uma SUGESTAO a confirmar, nunca uma afirmacao definitiva -- comece cada item com 'Sugestao:' e termine mencionando que precisa confirmacao. Lista vazia se nenhum proprietario for casado.",
            "onus_vigente": "lista de TEXTOS CURTOS (nao objetos/dicionarios -- strings prontas pra exibir), um por onus/gravame/restricao que NAO tem averbacao de baixa/cancelamento/quitacao registrada. Inclui: hipoteca, penhora, indisponibilidade, ALIENACAO FIDUCIARIA, arresto, cedula de credito, SERVIDAO (de passagem, administrativa, ou qualquer outra) (formato curto 'TIPO R-N' ou 'TIPO AV-N', ex: 'Alienação Fiduciária R-10', 'Servidão Administrativa AV-07' -- so' tipo e numero do registro/averbacao, SEM credor/beneficiario/valor/finalidade/detalhes -- ex CORRETO: 'Servidão Administrativa AV-07'; ex ERRADO (NAO faca isso): 'Servidão Administrativa AV-07 (em favor da Companhia X, destinada a Y) -- pode restringir uso da área e deve ser observada na lavratura' -- essa explicacao NAO deve aparecer pra servidao/hipoteca/penhora/etc, so' pros dois tipos citados a seguir) -- E TAMBEM usufruto e clausulas de inalienabilidade/impenhorabilidade/incomunicabilidade, mas esses dois ultimos tipos com uma frase curta explicando a implicacao pratica, nao so' o nome (ex: 'Usufruto R-2 -- usufrutuario precisa participar do ato', 'Inalienabilidade R-3 -- pode impedir a venda, verificar necessidade de autorizacao judicial'). Essa lista de tipos e' ilustrativa, nao exaustiva -- qualquer outro onus, gravame ou restricao real encontrado tambem entra, mesmo que nao esteja nomeado aqui (mas SEM explicacao extra, a nao ser que seja um dos dois tipos citados). Regra pra vigencia: sem baixa averbada, esta vigente, independente de quanto tempo passou. PRIORIDADE DE FONTE: se o documento tiver uma secao propria de 'Certidão de Ônus' (positiva ou negativa) com uma conclusao certificada pelo proprio cartorio (frase tipo 'CERTIFICO que consta o seguinte onus: ...' ou 'CERTIFICO que nao consta onus'), essa conclusao e' a fonte MAIS CONFIAVEL e deve prevalecer sobre qualquer inferencia feita lendo o historico de averbacoes por conta propria. Retorne 'nenhum' (string) se todos os onus/restricoes encontrados ja tiverem baixa averbada, ou se a certidao de onus (quando presente) certificar inexistencia de onus.",
            "descricao_ajustada_de_futuro_para_presente": "'sim' se a matricula descrevia o imovel como 'em construcao'/'a construir' e existe averbacao posterior de conclusao/'habite-se' -- e voce ajustou a descricao pro presente por causa disso; 'nao' caso contrario",
            "alertas_internos_matricula": "lista de inconsistencia notada DENTRO da propria matricula, MAS SOMENTE quando envolver: (a) o(s) PROPRIETARIO(S) ATUAL(IS) -- ex: grafia do nome ou numero de documento dele(s) mudou entre registros sem explicacao; ou (b) um ONUS que continua VIGENTE hoje. NAO liste inconsistencia sobre proprietarios ANTERIORES (quem ja vendeu/transferiu o imovel) nem sobre onus ja baixado -- essas pessoas nao vao assinar nada e essa informacao nao serve pra nada na lavratura. Lista vazia se nao notar nada relevante pelos criterios acima.",
            "data_ultima_alteracao_relevante": "data (DD/MM/AAAA) do ultimo registro (R-) ou averbacao (Av-) que MUDOU algo relevante pro estado atual (transmissao de propriedade, novo onus, baixa de onus, mudanca de estado civil de proprietario) -- ignore certidoes/reproducoes que so' atestam o estado sem mudar nada. Usada pra alertar se a matricula esta' 'desatualizada' ha' muito tempo.",
            "data_emissao_certidao": "data em que ESTA CERTIDAO/DOCUMENTO em si foi emitida ou impressa (geralmente perto de um carimbo/assinatura 'CERTIFICO...', 'Dou fe', ou rodape com data de emissao do documento -- NAO confundir com datas de registros/averbacoes internos). Formato DD/MM/AAAA. null se nao encontrar.",
            "historico_registros": "lista de objetos, um por CADA registro (R-) e averbacao (Av-/AV-) encontrado na matricula, na ordem em que aparecem, cada um com os campos: 'tipo' (ex: 'R-1', 'Av-5'), 'data' (DD/MM/AAAA), 'resumo' (uma frase curta, ate 15 palavras, do que aconteceu nesse registro -- ex: 'Compra e venda de Fulano para Ciclano', 'Hipoteca em favor do Banco X', 'Baixa da hipoteca do R-2'). Liste TODOS que encontrar, nao so' os mais recentes.",
        },
        "instrucoes_extras": """
IMPORTANTE -- como ler esta matricula:
Uma matricula e' um HISTORICO CUMULATIVO, nao um formulario com campos fixos.
Leia TODOS os registros (R-) e averbacoes (Av-) NA ORDEM CRONOLOGICA em que
aparecem, e determine o ESTADO ATUAL RESULTANTE -- nao pare no primeiro
registro que encontrar.

Regras de raciocinio obrigatorias:
1. PROPRIETARIO: o proprietario atual e' quem consta no ULTIMO registro de
   transmissao (R-), nao no R-1. Pode ter passado por varias transmissoes.
2. ONUS: procure QUALQUER tipo de gravame/restricao averbado -- hipoteca,
   penhora, indisponibilidade, ALIENACAO FIDUCIARIA (comum em compra
   financiada), usufruto, arresto, sequestro, ou qualquer outro. A REGRA
   PRA DECIDIR SE ESTA VIGENTE E' SIMPLES E MECANICA, NAO EXIGE CALCULO
   NENHUM: existe uma averbacao POSTERIOR de baixa/cancelamento/quitacao
   *daquele gravame especifico*? Se SIM, nao esta mais vigente. Se NAO
   existir essa averbacao de baixa, ENTAO ESTA VIGENTE -- ponto final.
   NUNCA tente estimar se um financiamento "ja deve ter terminado" pelo
   prazo contratado, data de inicio, etc. -- isso NAO e' um criterio
   valido. A UNICA coisa que importa e' se ha' ou nao uma averbacao de
   baixa registrada na propria matricula. Sem essa averbacao explicita,
   o gravame CONTINUA valendo, nao importa quantos anos tenham se passado.
3. DESCRICAO NO TEMPO: se a matricula descreve originalmente um imovel "a
   construir" ou "em construcao", procure se existe uma averbacao posterior
   de "conclusao de obra" ou "habite-se". Se existir, a descricao final deve
   estar no PRESENTE (imovel construido), nao repetir o texto original no
   futuro.
4. ALERTAS -- ESCOPO IMPORTANTE: quando notar grafia diferente do mesmo
   nome, numero de documento diferente, etc. em registros diferentes, SO'
   vale a pena registrar em "alertas_internos_matricula" se isso envolver
   o(s) PROPRIETARIO(S) ATUAL(IS) -- ou seja, quem ainda e' dono hoje, e
   vai ser parte no ato que se pretende lavrar. Inconsistencia sobre gente
   que ja vendeu/transferiu o imovel ha' muito tempo (proprietarios
   ANTERIORES na cadeia) NAO interessa -- essas pessoas nao vao assinar
   nada, entao a divergencia no nome/documento delas e' irrelevante pra
   lavratura. Excecao: se a inconsistencia estiver diretamente ligada a
   um ONUS que continua vigente, aí' sim vale mencionar, mesmo que seja
   sobre pessoa que nao e' mais proprietaria (ex: nome do credor diferente
   entre a averbacao do onus e outro lugar).
5. HISTORICO COMPLETO ("historico_registros"): diferente do resto dos
   campos (que so' querem o ESTADO FINAL), esse campo quer TODOS os
   registros/averbacoes, um por um, na ordem -- e' uma linha do tempo,
   nao um resumo. Nao pule nenhum, mesmo os que nao mudam o resultado
   final (ex: uma certidao anterior so' confirmando o estado, ou um
   registro sobre parte que ja nao e' mais proprietaria).
6. DATA DE EMISSAO DA CERTIDAO ("data_emissao_certidao"): isso e'
   DIFERENTE das datas dos registros/averbacoes dentro da matricula --
   e' a data em que ESSE DOCUMENTO/CERTIDAO especifico foi emitido ou
   impresso, geralmente perto de um carimbo, assinatura digital, "CERTIFICO
   que..." ou rodape de emissao. Usada pra calcular se a certidao ainda
   esta' dentro do prazo de validade (30 dias e' o prazo comum, mas quem
   usa esse dado decide isso, voce so' extrai a data).
7. SUGESTAO DE PARTICIPACAO DO CONJUGE: isso e' uma AJUDA, nao uma decisao
   juridica automatica -- sempre frase como sugestao a confirmar. Regra
   geral (nao absoluta): regime de comunhao (parcial ou universal) costuma
   exigir outorga/participacao do conjuge (art. 1.647 CC); separacao total
   de bens costuma dispensar. Ha' excecoes (ex: bem adquirido antes do
   casamento em comunhao parcial pode ser particular) -- por isso a
   sugestao deve sempre recomendar confirmacao, nunca afirmar com certeza.
""",
    },
    "pessoa_juridica": {
        "descricao": "Dados de uma pessoa juridica a partir de Contrato Social ou Estatuto",
        "campos": {
            "razao_social": "razao social completa",
            "cnpj": "numero do CNPJ, formatado 00.000.000/0000-00",
            "endereco_sede": "endereco completo da sede",
            "nome_representante_legal": "nome de quem assina/representa a empresa conforme o documento",
            "poderes_representante": "resumo dos poderes de representacao do signatario, se descritos",
            "eh_consolidado": "'sim' se o proprio documento se declara expressamente como Contrato Social/Estatuto Consolidado (reunindo todas as alteracoes anteriores em um so texto), 'nao' se parecer ser so uma alteracao contratual pontual (ex: 'primeira alteracao', 'aditivo'), 'indeterminado' se nao der pra saber",
            "data_do_documento": "data de assinatura/arquivamento deste documento especifico, formato DD/MM/AAAA",
            "numero_ultima_alteracao": "numero da alteracao contratual, se o documento se identificar como uma alteracao numerada (ex: '5a alteracao contratual')",
            "numero_registro_junta": "numero de registro do Contrato Social/Estatuto (ou de sua ultima alteracao) na Junta Comercial, se constar no proprio documento",
            "data_registro_junta": "data em que o Contrato Social/Estatuto (ou sua ultima alteracao) foi registrado na Junta Comercial, formato DD/MM/AAAA, se constar",
            "uf_junta_comercial": "UF (sigla do estado) da Junta Comercial onde a empresa esta registrada -- normalmente a mesma UF da sede, ex: 'PR'",
        },
    },
    "procuracao": {
        "descricao": "Procuracao Publica -- extrai tanto os dados do ATO de procuracao em si (onde/quando foi lavrada) quanto a qualificacao completa do PROCURADOR (a pessoa que recebe os poderes), que normalmente ja' vem descrita no proprio texto do instrumento",
        "campos": {
            "numero_tabeliao": "numero do Tabelionato de Notas onde a procuracao foi lavrada (ex: '8' de '8º Tabelionato')",
            "comarca_tabeliao": "cidade/comarca do Tabelionato onde foi lavrada, formato 'Cidade/UF'",
            "folhas": "numero das folhas onde foi lavrada no livro de notas original",
            "livro": "numero do livro de notas onde foi lavrada",
            "data_lavratura_procuracao": "data em que a procuracao foi lavrada, formato DD/MM/AAAA",
            "poderes_descritos": "resumo curto dos poderes conferidos, SO' se forem poderes limitados/especificos que valham a pena destacar. null se forem poderes gerais/amplos padrao.",
            "nome_procurador": "nome completo de quem RECEBE os poderes (o procurador -- nao quem outorga a procuracao)",
            "nacionalidade_procurador": "nacionalidade do procurador, JA GENERIZADA conforme o sexo dele -- 'brasileiro' ou 'brasileira', nunca 'brasileiro(a)' com parenteses.",
            "estado_civil_procurador": "APENAS a palavra do estado civil do procurador, JA GENERIZADA conforme o sexo -- 'solteiro'/'solteira', 'casado'/'casada' etc. NUNCA escreva com parenteses tipo 'casado(a)'. Sem regime de bens junto.",
            "sexo_procurador": "sexo do procurador, EXATAMENTE como consta no campo 'Sexo'/'Sex' do documento de identidade dele, se apresentado -- so' 'M' ou 'F'. Mesma logica do campo 'sexo' do schema 'pessoa': mais confiavel que inferir por nome/nacionalidade. null se nao tiver documento de identidade do procurador nesse conjunto (a procuracao em si pode ja' trazer nacionalidade/estado civil generizados no proprio texto, sem precisar de RG separado).",
            "profissao_procurador": "profissao do procurador, se constar",
            "rg_procurador": "numero do RG (Cedula de Identidade) do procurador -- presente tanto se o documento apresentado for o proprio RG quanto se for a CNH. ATENCAO: nos documentos de identidade em formato NOVO (a partir de ~2022), o RG e o CPF sao UNIFICADOS sob um unico campo 'Registro Geral-CPF' -- nesse formato, o numero do RG e' EXATAMENTE O MESMO numero do CPF. Se o documento apresentar esse campo unificado, copie o MESMO numero tanto para 'rg_procurador' quanto para 'cpf_procurador' -- NUNCA deixe vazio so' porque nao ha' um campo separado com rotulo 'RG'. Digito por digito com cuidado extra -- erros classicos de leitura sao confundir 0 (zero) com a letra O, 1 com I, e 5 com S.",
            "orgao_expedidor_procurador": "orgao expedidor do RG do procurador",
            "cpf_procurador": "numero do CPF do procurador, formatado 000.000.000-00",
            "endereco_procurador": "endereco completo do procurador, se constar",
        },
    },
    "comprovante_residencia": {
        "descricao": "Comprovante de residencia (conta de luz, agua, telefone, extrato bancario, etc.) -- usado so' pra extrair o endereco completo",
        "campos": {
            "endereco": "endereco completo tal como consta no comprovante -- rua, numero, complemento, bairro, cidade, UF e CEP, tudo junto formatado como endereco completo",
            "nome_titular": "nome da pessoa/empresa em nome de quem esta o comprovante, se constar",
            "data_documento": "data de emissao ou referencia do comprovante (ex: mes/ano da conta), formato disponivel no documento -- usado so' pra avaliar se o comprovante esta razoavelmente recente, nao tem uso na minuta em si",
        },
    },
    "certidao_estado_civil": {
        "descricao": "Certidao de estado civil de uma pessoa -- pode ser Certidao de Nascimento (pessoa solteira), Certidao de Casamento, ou Certidao de Casamento com uma averbacao posterior (divorcio, obito do conjuge, ou separacao judicial/extrajudicial). O documento em si diz qual e' -- veja o titulo/cabecalho e as averbacoes anotadas pra decidir.",
        "campos": {
            "tipo_documento": "'nascimento', 'casamento', 'casamento_com_averbacao_divorcio', 'casamento_com_averbacao_obito' (conjuge falecido, pessoa fica viuva), ou 'casamento_com_averbacao_separacao' (separacao judicial/extrajudicial -- diferente de divorcio: nao dissolve o casamento). Conforme o que o proprio documento se identifica como.",
            "numero_certidao": "numero de matricula/registro da certidao (o numero longo padrao CNS, ex: '083295 01 55 2013 2 00049 278 0010063 11')",
            "data_emissao": "data em que ESTA VIA/COPIA da certidao foi emitida (nao a data da celebracao do casamento/nascimento), formato DD/MM/AAAA",
            "cartorio_emissor": "nome do cartorio/serviço que EMITIU esta via da certidao (pode ser diferente do cartorio onde o casamento/nascimento foi originalmente registrado, ja' que certidao pode ser emitida por qualquer cartorio via sistema CRC) -- extraia so' o emissor desta via, ex: 'Serviço Distrital do Campo Comprido de Curitiba/PR'",
            "nome_conjuge": "nome completo do conjuge, SO' se for certidao de casamento (com ou sem qualquer averbacao). null se for certidao de nascimento.",
            "nome_pai": "nome completo do pai/genitor da pessoa titular da certidao, conforme campo 'Genitor(es)' ou 'Filiacao' do documento. Presente tanto em certidao de nascimento quanto de casamento. null se nao constar ou nao for identificavel qual dos dois genitores e' o pai.",
            "nome_mae": "nome completo da mae/genitora da pessoa titular da certidao, mesma logica do campo nome_pai. null se nao constar.",
            "data_casamento": "data da celebracao do casamento, formato DD/MM/AAAA. null se for certidao de nascimento.",
            "regime_bens": "regime de bens do casamento (ex: 'comunhao parcial de bens'), incluindo referencia a lei se mencionado (ex: 'na vigencia da Lei 6.515/77'). null se for certidao de nascimento.",
            "tem_averbacao_divorcio": "true se o documento tiver averbacao de divorcio anotada, false caso contrario",
            "data_divorcio": "data da averbacao/decisao de divorcio, formato DD/MM/AAAA, SO' se tem_averbacao_divorcio for true. null caso contrario.",
            "tem_averbacao_obito": "true se o documento tiver averbacao de obito do conjuge anotada, false caso contrario",
            "data_obito": "data da averbacao de obito do conjuge, formato DD/MM/AAAA, SO' se tem_averbacao_obito for true. null caso contrario.",
            "tem_averbacao_separacao": "true se o documento tiver averbacao de separacao judicial/extrajudicial anotada (e NAO tiver divorcio posterior -- se tiver os dois, o divorcio e' o que vale, marque so' tem_averbacao_divorcio), false caso contrario",
            "data_separacao": "data da averbacao de separacao, formato DD/MM/AAAA, SO' se tem_averbacao_separacao for true. null caso contrario.",
            "outras_averbacoes_relevantes": "texto livre descrevendo qualquer OUTRA averbacao ou situacao fora do padrao que o documento mostre e que possa ser relevante pra qualificacao das partes -- ex: mais de um casamento anterior averbado, indicio de interdicao/curatela, uniao estavel convertida em casamento, ou qualquer anotacao incomum. Descreva em 1-2 frases o que encontrou, pra virar um alerta de conferencia manual. null se nao notar nada fora do padrao ja' coberto pelos campos acima.",
        },
    },
    "falecido": {
        "descricao": "Dados do autor da heranca (falecido/de cujus) para escritura de INVENTARIO, combinando qualificacao pessoal, dados do obito e da negativa de testamento. Normalmente extraido de um conjunto de documentos: RG/CNH do falecido, certidao de obito, e informacao negativa de testamento (CENSEC).",
        "campos": {
            "nome": "nome completo do falecido",
            "nacionalidade": "nacionalidade, JA GENERIZADA conforme o sexo -- 'brasileiro' ou 'brasileira'.",
            "sexo": "sexo do falecido, EXATAMENTE como consta no campo 'Sexo'/'Sex' do RG/CNH dele, se apresentado -- so' 'M' ou 'F'. Mesma logica do campo 'sexo' do schema 'pessoa': muito mais confiavel que inferir por nacionalidade/nome. null so' se nao houver documento de identidade do falecido no conjunto (as vezes so' vem a certidao de obito, sem RG/CNH -- nesse caso o genero cai no sinal mais fraco de nacionalidade/estado_civil).",
            "profissao": "profissao declarada, SOMENTE se estiver EXPLICITAMENTE escrita no documento. NUNCA infira a partir de idade/sexo/estado civil. null e' o valor esperado na maioria dos casos.",
            "naturalidade": "cidade e UF de nascimento, se constar. null se nao constar.",
            "data_nascimento": "data de nascimento, formato DD/MM/AAAA, se constar. null se nao constar.",
            "nome_pai": "nome completo do pai do falecido, se constar (ex: em certidao de nascimento ou casamento dele). null se nao constar.",
            "nome_mae": "nome completo da mae do falecido, mesma logica. null se nao constar.",
            "rg": "numero do RG, com o mesmo cuidado de leitura digito-a-digito (0/O, 1/I, 5/S) e a mesma regra de RG=CPF unificado em documentos novos (ver schema 'pessoa' pra detalhe completo dessa regra).",
            "orgao_expedidor": "orgao expedidor do RG, SEMPRE ABREVIADO (ex: 'SSP/UF', 'IIPR/PR') -- mesma regra do schema 'pessoa'.",
            "cpf": "numero do CPF, formatado 000.000.000-00",
            "endereco": "endereco onde o falecido era residente e domiciliado, se constar (pode vir do RG ou de outro documento apresentado).",
            "estado_civil": "estado civil do falecido AO TEMPO DO FALECIMENTO, JA GENERIZADO conforme o sexo -- 'solteiro'/'solteira', 'casado'/'casada', 'divorciado'/'divorciada', 'viuvo'/'viuva' ou 'separado'/'separada'. NUNCA escreva com parenteses tipo 'casado(a)'. NAO inclua regime de bens aqui.",
            "regime_bens": "regime de bens do casamento, SO' se estado_civil for 'casado(a)' e isso constar no documento (ex: certidao de casamento). Inclua referencia a lei se mencionado (ex: 'na vigencia da Lei 6.515/77'). null se nao se aplicar ou nao constar.",
            "nome_conjuge_sobrevivente": "nome completo do conjuge, SO' se o falecido era casado(a) E o conjuge esta' vivo (viuvo(a) meeiro(a) do inventario). Se a certidao de casamento tiver averbacao de obito do CONJUGE (ou seja, o conjuge morreu ANTES do falecido/de cujus), retorne null aqui -- nesse caso nao ha' viuvo(a) meeiro(a) no presente inventario.",
            "data_falecimento": "data do falecimento, formato DD/MM/AAAA, conforme a certidao de obito.",
            "hora_falecimento": "horario do falecimento, formato HH:MM, se constar na certidao de obito. null se nao constar.",
            "local_falecimento_tipo": "'hospital' se o falecimento ocorreu em unidade de saude/hospital, ou 'domicilio' se ocorreu em residencia -- conforme a certidao de obito discrimina.",
            "local_falecimento_descricao": "se local_falecimento_tipo for 'hospital', o NOME do hospital/unidade de saude. Se for 'domicilio', o ENDERECO completo do domicilio onde ocorreu o obito. Extraia so' o que o tipo escolhido pedir.",
            "cidade_falecimento": "cidade onde ocorreu o falecimento",
            "uf_falecimento": "UF (sigla) onde ocorreu o falecimento",
            "obito_matricula": "numero de matricula da certidao de obito (numero longo padrao CNS, ex: '083295 01 55 2024 2 00049 278 0010063 11')",
            "obito_oficio_registro": "nome/numero do oficio de registro civil onde o obito foi registrado (ex: '2º Serviço de Registro Civil das Pessoas Naturais')",
            "obito_comarca_uf": "comarca e UF onde fica o oficio de registro do obito (ex: 'Curitiba/PR')",
            "obito_data_extracao_certidao": "data em que ESTA VIA da certidao de obito foi extraida/emitida (diferente da data do falecimento em si), formato DD/MM/AAAA",
            "obito_arquivamento_folhas": "numero de folhas onde a certidao de obito fica arquivada digitalmente nesta serventia, se essa informacao estiver no documento (geralmente e' uma anotacao do proprio cartorio de notas, pode nao constar no documento de origem -- null se nao constar).",
            "obito_arquivamento_livro": "numero do livro (formato tipo '000000-D') onde a certidao de obito fica arquivada nesta serventia, mesma logica do campo acima -- null se nao constar no documento.",
            "testamento_negativa_data": "data de emissao da informacao NEGATIVA de testamento expedida pela CENSEC (Central Notarial de Servicos Eletronicos Compartilhados), formato DD/MM/AAAA. null se esse documento nao foi apresentado no conjunto.",
            "testamento_negativa_referencia": "numero de referencia/protocolo da informacao negativa de testamento da CENSEC. null se nao apresentado.",
        },
    },
    "certidao_simplificada": {
        "descricao": "Dados de uma Certidao Simplificada emitida pela Junta Comercial",
        "campos": {
            "razao_social": "razao social completa",
            "cnpj": "numero do CNPJ, formatado 00.000.000/0000-00",
            "nire": "Numero de Identificacao do Registro de Empresas, se constar",
            "ultimo_arquivamento_data": "data do ultimo arquivamento registrado na Junta Comercial, formato DD/MM/AAAA",
            "ultimo_arquivamento_numero": "numero do ultimo arquivamento/protocolo",
            "ultimo_arquivamento_ato": "natureza do ultimo ato arquivado (ex: 'alteracao contratual', 'consolidacao', 'transformacao')",
            "administrador_atual": "nome do(s) administrador(es)/representante(s) legal(is) atual(is) conforme a certidao",
            "data_emissao": "data em que ESTA certidao simplificada foi emitida/expedida pela Junta Comercial (diferente da data do ultimo arquivamento), formato DD/MM/AAAA",
        },
    },
    "certidao": {
        "descricao": "Certidao apresentada por uma das partes (fiscal, trabalhista, de distribuidor/feitos ajuizados, etc.) -- schema generico, usado pra qualquer um dos tipos: Debitos Trabalhistas, Feitos Ajuizados 1a/2a Distribuidor, Feitos Ajuizados de comarca diferente, Feitos Ajuizados TRT, Feitos Ajuizados TRF, Tributos Federais, Tributos Estaduais",
        "campos": {
            "numero": "numero/protocolo/codigo de identificacao da propria certidao -- ATENCAO ESPECIAL: em certidoes de Tributos Federais (RFB/PGFN), esse numero quase sempre aparece sob o rotulo 'Código de controle da certidão' (formato alfanumerico com pontos, ex: '4E97.F7D3.B862.A18F') -- isso CONTA como o numero da certidao, mesmo nao tendo a palavra 'numero' no rotulo; copie o codigo completo, com pontos e tudo. Em outras certidoes, procure rotulos como 'numero da certidao' ou 'protocolo'. Muitas certidoes de distribuidor/feitos ajuizados NAO tem numero proprio, so' um numero de protocolo de emissao ou nenhum numero visivel -- nesses casos, retorne null. Nunca invente um numero.",
            "situacao": "'negativa' se a certidao atesta que NAO ha' debito/feito/acao (ex: 'nada consta', 'certidao negativa'); 'positiva' se acusa a existencia de debito/feito/acao pendente; 'positiva com efeito de negativa' se o documento usar exatamente essa expressao (comum quando ha' debito mas com exigibilidade suspensa/parcelado). Copie a terminologia mais proxima do que o documento efetivamente diz.",
            "data_emissao": "data de emissao/expedicao da certidao, formato DD/MM/AAAA",
            "data_validade": "data de validade/vencimento, se constar explicitamente escrita no documento -- em DUAS formas possiveis, ambas contam: (1) uma data explicita 'valida ate DD/MM/AAAA'; OU (2) um prazo relativo tipo 'validade de N dias' / 'valida por N (por extenso) dias da data de expedicao' -- NESSE CASO, SEMPRE calcule e devolva a data final (data_emissao + N dias), nunca deixe o campo vazio so' porque o documento nao escreveu a data final ja' calculada. Exemplo: documento com data_emissao 09/09/2026 e texto 'valida por 30 (trinta) dias da data de expedicao' -> data_validade deve ser '09/10/2026'. So' retorne null se o documento genuinamente nao mencionar NENHUM prazo (nem data fixa, nem numero de dias).",
            "orgao_emissor": "nome COMPLETO do orgao/tribunal/site que emitiu a certidao, incluindo a REGIAO/CIRCUNSCRICAO/INSTANCIA quando aparecer no cabecalho do documento (ex: 'Receita Federal do Brasil', 'TRT da 9a Regiao', 'Justica Federal da 4a Regiao', 'TJPR - 1o Distribuidor de Curitiba'). NAO omita a regiao/numero mesmo que ja tenha extraido esse dado em certidao parecida de outra pessoa no mesmo caso -- releia o cabecalho DESTE documento especifico.",
        },
    },
}


def escolher_condicao_dispensa_certidao(tipo_certidao_id: str) -> str:
    """Mapeia o id interno de cada tipo de certidao pra o nome da
    condicao de dispensa correspondente no motor de minuta (usado pelo
    backend ao montar o dict de 'condicoes' quando uma certidao nao foi
    enviada). Centralizado aqui pra so' existir UM lugar com essa lista
    de 8 tipos -- se um tipo mudar de nome, muda so aqui."""
    return f"certidao_{tipo_certidao_id}_dispensada"


# Os 8 tipos de certidao fixos definidos com o usuario, na ordem que
# aparecem no card de cada parte (fora a matricula/onus, que ja e' o
# tipo "imovel" tratado a parte). "feitos_comarca_diferente" e' o unico
# que nao aparece sempre -- so' quando a pessoa clicar em "+ Adicionar
# comarca diferente" no front, por isso NAO tem um slot fixo, e sim uma
# lista (pode ter zero, um, ou mais arquivos desse tipo por pessoa).
TIPOS_CERTIDAO = [
    ("debitos_trabalhistas", "Certidão de Débitos Trabalhistas"),
    ("feitos_1_distribuidor", "Certidão de Feitos Ajuizados — 1º Distribuidor"),
    ("feitos_2_distribuidor", "Certidão de Feitos Ajuizados — 2º Distribuidor"),
    ("feitos_trt", "Certidão de Feitos Ajuizados — TRT"),
    ("feitos_trf", "Certidão de Feitos Ajuizados — TRF"),
    ("tributos_federais", "Certidão de Tributos Federais"),
    ("tributos_estaduais", "Certidão de Tributos Estaduais"),
]
# "feitos_comarca_diferente" fica de fora dessa lista fixa de proposito
# (ver comentario acima) -- tratado separadamente como lista opcional.

# So' essas 3 admitem a clausula de dispensa por declaracao das partes
# ("as partes, cientes dos riscos... dispensam expressamente..."), regra
# combinada com o usuario. As outras 4 (debitos_trabalhistas, feitos_trf,
# tributos_federais, tributos_estaduais) sao OBRIGATORIAS -- se faltarem,
# viram pendencia visivel (bloco de status na tela de confirmacao +
# alerta critico no .docx), nunca uma dispensa silenciosa.
CERTIDOES_DISPENSAVEIS_POR_DECLARACAO = {
    "feitos_1_distribuidor", "feitos_2_distribuidor", "feitos_trt",
}


def verificar_consolidacao_pj(dados_contrato: dict, dados_simplificada: dict | None) -> list[str]:
    """
    Cruza o Contrato Social/Estatuto apresentado com a Certidao Simplificada
    (Junta Comercial), gerando pontos de atencao quando nao da pra confirmar
    que o contrato apresentado e' o mais atual.

    Isso NUNCA decide sozinho se esta tudo certo -- so aponta divergencia pra
    o escrevente conferir, seguindo a mesma logica do relatorio de matricula.
    """
    alertas = []

    if not dados_simplificada:
        alertas.append(
            "Certidão Simplificada da Junta Comercial não foi apresentada — não é "
            "possível confirmar se o Contrato Social/Estatuto apresentado é o mais atual."
        )
        return alertas

    if dados_contrato.get("eh_consolidado") == "nao":
        alertas.append(
            "O documento apresentado parece ser uma alteração contratual pontual, "
            "não um Contrato Social Consolidado. Verifique se reúne todas as "
            "cláusulas vigentes ou se falta juntar o contrato original + alterações."
        )

    data_doc = dados_contrato.get("data_do_documento")
    data_ultimo = dados_simplificada.get("ultimo_arquivamento_data")
    if data_doc and data_ultimo and data_doc != data_ultimo:
        alertas.append(
            f"Data do documento apresentado ({data_doc}) diverge do último "
            f"arquivamento constante na Certidão Simplificada ({data_ultimo}) — "
            f"pode existir alteração posterior não apresentada."
        )

    cnpj_doc = dados_contrato.get("cnpj")
    cnpj_simpl = dados_simplificada.get("cnpj")
    if cnpj_doc and cnpj_simpl and cnpj_doc != cnpj_simpl:
        alertas.append(
            f"CNPJ do Contrato Social ({cnpj_doc}) diverge do CNPJ da Certidão "
            f"Simplificada ({cnpj_simpl}) — confira se são o mesmo documento/empresa."
        )

    return alertas


# Modelo padrao (documento com variacao de qualidade -- foto, escaneado
# torto, sem formato fixo): Sonnet 5, bom equilibrio custo/precisao.
MODELO_PADRAO = "claude-sonnet-5"

# Excecoes por tipo de documento:
# - "certidao_simplificada": documento nascido digital (Junta Comercial),
#   texto limpo e formato padronizado -- candidato seguro pro modelo mais
#   barato. Ainda vale validar com uns 10-15 documentos reais antes de
#   confiar 100% em producao (ver conversa sobre isso).
# NOTA: "imovel" (matricula) NAO tem excecao fixa aqui -- ver
# escolher_modelo_matricula() abaixo. A tarefa de achar par onus/baixa e'
# conferencia estruturada, nao raciocinio aberto -- o prompt ja da' a regra
# pronta ("procure se existe averbacao posterior de cancelamento"). Sonnet
# resolve bem a maioria dos casos; so' escala pra Opus quando a matricula e'
# longa o suficiente pra ter risco real de "perder o fio" no meio do
# historico (nao por falta de inteligencia, por tamanho de contexto).
MODELO_POR_TIPO = {
    "certidao_simplificada": "claude-haiku-4-5-20251001",
}

# Migracao GRADUAL de mais tipos de certidao pro Haiku (mais barato: $1/$5
# por milhao de tokens vs $2/$10 do Sonnet). Comecando SO' pelas 2 mais
# seguras: certidoes de tributos (federal e estadual) sao emitidas por
# portal de governo com layout de texto plano, fixo e padronizado (RFB/
# PGFN e Secretaria da Fazenda estadual) -- bem menos variacao visual que
# certidoes judiciais (TRT/TRF/distribuidores), que mudam de formato
# dependendo do tribunal/regiao e tem mais nuance de redacao.
#
# ATENCAO -- igual foi feito com certidao_simplificada: NAO promover mais
# tipos pra essa lista sem antes rodar uns 10-15 documentos REAIS de cada
# tipo e comparar a extracao lado a lado com o resultado que o Sonnet dava
# antes. O log de extracao (extracao_log.py / tabela extracoes_log) ja'
# registra o modelo usado por chamada -- usar isso pra auditar depois de
# um tempo em producao, nao so' confiar que "documento parece simples".
MODELO_POR_TIPO_CERTIDAO = {
    "tributos_federais": "claude-haiku-4-5-20251001",
    "tributos_estaduais": "claude-haiku-4-5-20251001",
}

# Acima desse numero de paginas, a matricula escala pro modelo mais forte.
# Numero exploratorio -- ajustar conforme os primeiros testes reais.
LIMITE_PAGINAS_MATRICULA_LONGA = 8


def _contar_paginas_pdf(caminho_arquivo: str) -> int | None:
    """Conta paginas de um PDF pra estimar o tamanho da matricula. Retorna
    None se nao for PDF ou se nao conseguir ler (nesse caso, assume-se o
    caminho seguro/mais barato -- ver escolher_modelo_matricula)."""
    if not caminho_arquivo.lower().endswith(".pdf"):
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(caminho_arquivo).pages)
    except Exception:
        return None


def escolher_modelo_matricula(caminho_arquivo: str) -> str:
    """Sonnet por padrao; escala pra Opus so' quando a matricula e' longa
    (muitas paginas -- proxy pra muitos registros/averbacoes), onde o risco
    de esquecer de casar um onus com sua baixa la' na frente do documento
    e' maior. Imagem unica (jpg/png) fica sempre no Sonnet, ja' que nao da'
    pra estimar "historico longo" a partir de uma imagem so'."""
    paginas = _contar_paginas_pdf(caminho_arquivo)
    if paginas is not None and paginas > LIMITE_PAGINAS_MATRICULA_LONGA:
        return "claude-opus-4-8"
    return MODELO_PADRAO


# Limiar pratico pra decidir se uma PAGINA especifica de um PDF e' "nascida
# digital" (tem texto de verdade) ou e' uma imagem/foto sem OCR embutido
# (nesse caso extract_text() devolve None/"" ou so' lixo). Uma pagina de
# texto real (mesmo curta, tipo uma certidao de 1 pagina) tem centenas de
# caracteres; uma foto de RG/CNH devolve 0.
_MIN_CARACTERES_PAGINA_TEXTO_NATIVO = 40


def _extrair_texto_nativo_pdf(caminho_arquivo: str, permitir_pular_paginas_sem_texto: bool = False) -> str | None:
    """Se TODAS as paginas do PDF forem nascidas digitais, devolve o texto
    de todas elas concatenado -- MUITO mais barato que mandar a mesma
    pagina como imagem (que e' cobrada em tokens de visao), e sem risco
    de erro de leitura visual (0/O, 1/I, 5/S etc.) ja' que o texto vem
    exato do PDF.

    Se QUALQUER pagina do documento nao tiver texto suficiente (ou seja,
    for uma foto/scan -- tipo a pagina do RG dentro de um PDF combinado
    de pessoa), o comportamento PADRAO e' devolver None pro DOCUMENTO
    INTEIRO, mesmo que as outras 9 paginas sejam texto puro -- NAO da'
    pra misturar "texto de umas paginas + imagem de outras" num unico
    bloco de mensagem hoje, e errar nessa checagem tem custo alto: um PDF
    combinado de pessoa (RG/CNH + certidoes) tem a foto do RG numa pagina
    e texto puro nas certidoes -- se a checagem fosse feita so' pela
    MEDIA de caracteres do documento inteiro (a primeira versao desta
    funcao, JAMAIS FAZER ISSO DE NOVO), a media alta das paginas de
    certidao escondia a pagina 100% vazia do RG, e o documento inteiro
    virava texto -- ou seja, a IA nunca via a foto do RG e a extracao de
    identidade (nome/RG/CPF) saia toda vazia. Confirmado na pratica com
    Documentos_Maria_Marzola.pdf: paginas 1-2 (RG e formulario de
    endereco, ambas imagem) tem 0 caracteres, mas a MEDIA do documento
    passava de boa no limiar por causa das paginas de certidao (texto
    denso) -- por isso o criterio padrao e' por PAGINA (TODAS acima do
    limiar), nunca pela media do documento inteiro.

    'permitir_pular_paginas_sem_texto=True' MUDA esse comportamento: em
    vez de reprovar o documento inteiro por causa de 1 pagina fraca, so'
    PULA as paginas fracas e devolve o texto so' das paginas boas (None
    apenas se NENHUMA pagina tiver texto). Isso SO' e' seguro de usar
    quando a tarefa que vai ler esse texto genuinamente nao precisa ver
    as paginas de imagem puladas -- que e' exatamente o caso da busca de
    certidao dentro do PDF combinado (schema "certidao" com
    contexto_extra): uma foto de RG/CNH NUNCA vai conter uma certidao,
    entao pular essa pagina nao perde informacao nenhuma relevante pra
    essa tarefa especifica. NAO usar esse modo pra schema "pessoa"
    (precisa da foto do RG) nem pra qualquer chamada onde nao se possa
    garantir de antemao que as paginas puladas sao irrelevantes."""
    try:
        from pypdf import PdfReader
        paginas = PdfReader(caminho_arquivo).pages
        textos = [(pagina.extract_text() or "") for pagina in paginas]
    except Exception:
        return None  # PDF corrompido, protegido por senha, etc. -- cai pra imagem

    if not textos:
        return None

    if permitir_pular_paginas_sem_texto:
        textos_bons = [t for t in textos if len(t.strip()) >= _MIN_CARACTERES_PAGINA_TEXTO_NATIVO]
        if not textos_bons:
            return None  # nenhuma pagina tem texto -- documento e' 100% imagem/scan
        return "\n\n--- (nova pagina) ---\n\n".join(textos_bons)

    if any(len(t.strip()) < _MIN_CARACTERES_PAGINA_TEXTO_NATIVO for t in textos):
        return None  # pelo menos 1 pagina e' foto/scan -- documento inteiro cai pra imagem
    return "\n\n--- (nova pagina) ---\n\n".join(textos)



def extrair(caminho_arquivo: str, tipo: str, modelo: str | None = None, contexto_extra: str | None = None, permitir_pular_paginas_sem_texto: bool = False) -> dict:
    if tipo not in SCHEMAS:
        raise ValueError(f"tipo deve ser um de: {list(SCHEMAS)}")

    if modelo:
        modelo_usado = modelo
    elif tipo == "imovel":
        modelo_usado = escolher_modelo_matricula(caminho_arquivo)
    else:
        modelo_usado = MODELO_POR_TIPO.get(tipo, MODELO_PADRAO)

    client = anthropic.Anthropic()  # le ANTHROPIC_API_KEY do ambiente

    with open(caminho_arquivo, "rb") as f:
        dados_binarios = f.read()
    b64 = base64.standard_b64encode(dados_binarios).decode("utf-8")

    ext = caminho_arquivo.lower().split(".")[-1]
    media_type = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }.get(ext, "image/jpeg")

    schema = SCHEMAS[tipo]
    campos_txt = "\n".join(f"- {k}: {v}" for k, v in schema["campos"].items())

    # Instrucao fixa (sempre igual pra um mesmo "tipo") vai como SYSTEM PROMPT,
    # com cache_control ligado. Assim a Anthropic reaproveita esse texto ja
    # processado nas chamadas seguintes (mesmo tipo de documento), cobrando so
    # 10% do preco normal de entrada nessa parte -- so o documento em si (que
    # muda a cada chamada) e' cobrado no preco cheio. Cache valido por 5 min;
    # como normalmente processamos varios documentos da mesma escritura em
    # sequencia, a maioria das chamadas cai dentro dessa janela.
    system_prompt = [
        {
            "type": "text",
            "text": f"""Voce e' um assistente de um escrevente notarial brasileiro.
Leia o documento anexado ({schema['descricao']}) e extraia os seguintes campos.

{campos_txt}
{schema.get('instrucoes_extras', '')}
Regras:
- Responda APENAS com um objeto JSON valido, sem markdown, sem explicacao.
- Se um campo nao aparecer no documento, use null.
- Nao invente informacao que nao esteja no documento.
- Para CPF e RG, mantenha a formatacao original do documento.
""",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # 'contexto_extra' e' usado quando o MESMO schema generico ("certidao")
    # e' chamado varias vezes seguidas contra o MESMO arquivo COMBINADO
    # (PDF unico que junta identidade + 7 certidoes negativas diferentes,
    # ou matricula + certidao de IPTU) -- sem isso, a IA nao tem como
    # saber qual das VARIAS certidoes presentes no arquivo ela deve achar
    # em cada chamada especifica, e o resultado sai errado ou vazio
    # mesmo quando o documento certo esta' la' dentro. Fica em um bloco
    # SEPARADO do cache (o texto muda a cada chamada, entao nao faz
    # sentido colocar isso na parte cacheada, que precisa ser identica
    # pra reaproveitar o cache).
    if contexto_extra:
        system_prompt.append({"type": "text", "text": contexto_extra})

    # Matricula pode ter historico longo (varios registros/averbacoes) e o
    # raciocinio cronologico pede mais espaco de saida (lista de onus,
    # alertas internos) -- da mais folga de tokens só' pra esse tipo.
    # Matricula precisa de bem mais espaco que os outros documentos:
    # alem da resposta em si (relatorio com onus, alertas, etc.), o
    # modelo mais forte usado aqui (Opus, ver MODELO_POR_TIPO) gasta
    # parte do orcamento de tokens "pensando" antes de escrever a
    # resposta final -- se o limite for baixo, ele estoura pensando e
    # nunca chega a escrever o JSON. 2048 nao era suficiente na pratica
    # pro imovel (por isso o imovel usa 8000) -- e o schema de "pessoa"
    # cresceu bastante desde que 1024 foi definido (11 campos hoje,
    # varios com instrucao longa), entao subimos o padrao tambem, pra
    # evitar resposta cortada no meio (erro classico: "Unterminated
    # string", JSON invalido por falta de espaco pra terminar).
    max_tokens = 8000 if tipo == "imovel" else 2048

    timeout_segundos = TIMEOUT_IMOVEL_SEGUNDOS if tipo == "imovel" else TIMEOUT_PADRAO_SEGUNDOS
    doc_block_type = "document" if media_type == "application/pdf" else "image"

    # PDF nascido digital (a grande maioria das certidoes emitidas por
    # portal de governo, e a matricula quando exportada em PDF real, nao
    # escaneada) -- manda como TEXTO em vez de imagem/documento. Isso e'
    # preferido a imagem em praticamente todos os casos: mais barato (bem
    # menos tokens por pagina) e mais exato (sem risco de erro de leitura
    # visual). So' cai pro fluxo de imagem/documento (abaixo) quando o
    # arquivo e' de fato uma foto/scan (RG, CNH, foto de documento) --
    # esses nunca tem camada de texto, entao _extrair_texto_nativo_pdf
    # devolve None e nada muda pra eles.
    #
    # 'permitir_pular_paginas_sem_texto' e' um parametro EXPLICITO (default
    # False, conservador) que o CHAMADOR decide, nao mais inferido daqui
    # so' por tipo=="certidao"+contexto_extra. Motivo da mudanca: a
    # inferencia automatica ERA insegura pro caso da certidao municipal do
    # imovel (busca dentro do PDF UNICO combinado do imovel: matricula +
    # onus + certidao de tributos municipais). Nesse caso, ao contrario do
    # PDF de pessoa (onde a unica pagina fraca e' sempre o RG/CNH, que
    # NUNCA e' a certidao procurada), a propria certidao municipal pode
    # SER a pagina fraca/imagem (muitas prefeituras emitem essa certidao
    # como PDF escaneado/rasterizado, sem camada de texto) -- pular essa
    # pagina jogava fora exatamente o dado que a busca precisava encontrar,
    # fazendo a certidao de tributos municipais do imovel sair sempre em
    # branco mesmo quando o documento estava la' no arquivo combinado.
    # Confirmado testando com Matricula_merged.pdf real: pagina 5 (a
    # certidao da Prefeitura de Curitiba) tem 0 caracteres de texto nativo,
    # enquanto as paginas 1-4 (matricula/onus) tem texto normal.
    #
    # Por isso agora so' o fluxo de PESSOA
    # (_extrair_certidoes_pessoa_combinado em main.py) liga essa flag
    # explicitamente; o fluxo de certidao municipal do imovel deixa no
    # padrao False -- sempre manda o documento/imagem completo, igual
    # sempre foi, sem risco de pular a pagina certa.
    texto_nativo = (
        _extrair_texto_nativo_pdf(caminho_arquivo, permitir_pular_paginas_sem_texto=permitir_pular_paginas_sem_texto)
        if media_type == "application/pdf" else None
    )

    if texto_nativo:
        bloco_documento = {
            "type": "text",
            "text": (
                "[Conteudo abaixo extraido diretamente da camada de texto do PDF "
                "(documento nascido digital) -- texto exato, sem risco de erro de "
                "leitura visual]\n\n" + texto_nativo
            ),
        }
    else:
        bloco_documento = {
            "type": doc_block_type,
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64,
            },
        }

    # Cache do PROPRIO documento (nao so' da instrucao): quando
    # 'contexto_extra' vem preenchido, e' porque esse MESMO arquivo vai
    # ser lido varias vezes em sequencia (as ~11 tentativas de certidao
    # contra o PDF unico combinado -- ver _extrair_certidoes_pessoa_combinado
    # em main.py). Sem isso, cada uma dessas chamadas pagava o preco
    # cheio de input pra reenviar o mesmo documento inteiro de novo; com
    # cache_control aqui, so' a PRIMEIRA chamada paga preco cheio, as
    # demais (dentro da janela de 5 min do cache) pagam so' 10% da parte
    # do documento. Vale tanto pro bloco de texto quanto pro de
    # imagem/documento -- deliberadamente NAO habilitado quando nao ha'
    # contexto_extra (documentos lidos uma unica vez, como RG/CNH
    # avulsos) -- cache write custa 1.25x o preco normal, entao so'
    # compensa quando o mesmo documento e' de fato reaproveitado.
    if contexto_extra:
        bloco_documento["cache_control"] = {"type": "ephemeral"}

    inicio = time.time()
    try:
        message = client.messages.create(
            model=modelo_usado,
            max_tokens=max_tokens,
            system=system_prompt,
            timeout=timeout_segundos,
            messages=[
                {
                    "role": "user",
                    "content": [bloco_documento],
                }
            ],
        )
    except anthropic.APITimeoutError:
        tempo_decorrido = time.time() - inicio
        registrar_extracao(tipo, modelo_usado, tempo_decorrido, sucesso=False,
                            erro=f"timeout apos {timeout_segundos}s")
        raise TimeoutError(
            f"A IA não respondeu em {timeout_segundos}s ao tentar ler este "
            f"documento ({schema['descricao']}). Pode ser instabilidade "
            f"temporária de rede ou da API -- tente novamente. Se continuar "
            f"acontecendo, confira o documento (arquivo grande demais, "
            f"corrompido, ou ilegível)."
        )
    except Exception as e:
        tempo_decorrido = time.time() - inicio
        registrar_extracao(tipo, modelo_usado, tempo_decorrido, sucesso=False, erro=str(e))
        raise

    tempo_decorrido = time.time() - inicio
    uso = getattr(message, "usage", None)
    input_tokens = getattr(uso, "input_tokens", None) if uso else None
    output_tokens = getattr(uso, "output_tokens", None) if uso else None
    cache_creation_tokens = getattr(uso, "cache_creation_input_tokens", None) if uso else None
    cache_read_tokens = getattr(uso, "cache_read_input_tokens", None) if uso else None

    # A resposta pode vir com mais de um bloco (ex: um bloco de "thinking"
    # antes do texto, em modelos com raciocinio estendido) -- procura
    # especificamente o bloco de tipo "text", em vez de assumir que e'
    # sempre o primeiro item da lista.
    bloco_texto = next((b for b in message.content if getattr(b, "type", None) == "text"), None)
    if bloco_texto is None:
        motivo_parada = getattr(message, "stop_reason", "desconhecido")
        registrar_extracao(tipo, modelo_usado, tempo_decorrido, input_tokens, output_tokens,
                            sucesso=False, erro=f"sem bloco de texto (stop_reason={motivo_parada})",
                            cache_creation_tokens=cache_creation_tokens, cache_read_tokens=cache_read_tokens)
        raise ValueError(
            f"A resposta da IA não trouxe nenhum bloco de texto (motivo de parada: "
            f"'{motivo_parada}'). Se for 'max_tokens', o limite estourou antes do "
            f"modelo terminar de responder -- tente novamente ou reporte esse erro "
            f"pra aumentar o limite ainda mais."
        )

    texto = bloco_texto.text.strip()
    # remove eventuais cercas de markdown que o modelo possa ter colocado
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]

    try:
        resultado = json.loads(texto)
    except json.JSONDecodeError as e:
        registrar_extracao(tipo, modelo_usado, tempo_decorrido, input_tokens, output_tokens,
                            sucesso=False, erro=f"JSON invalido: {e}",
                            cache_creation_tokens=cache_creation_tokens, cache_read_tokens=cache_read_tokens)
        motivo_parada = getattr(message, "stop_reason", None)
        if motivo_parada == "max_tokens":
            raise ValueError(
                f"A resposta da IA foi cortada no meio (estourou o limite de {max_tokens} tokens "
                f"antes de terminar). Tente novamente -- se continuar acontecendo com esse mesmo "
                f"documento, ele pode ter texto incomum demais pra esse tipo de extração."
            )
        raise ValueError(
            f"A resposta da IA não veio em formato JSON válido (erro: {e}). Tente novamente -- "
            f"pode ter sido uma instabilidade pontual."
        )

    registrar_extracao(tipo, modelo_usado, tempo_decorrido, input_tokens, output_tokens, sucesso=True,
                            cache_creation_tokens=cache_creation_tokens, cache_read_tokens=cache_read_tokens)
    return resultado


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--tipo", required=True, choices=list(SCHEMAS))
    args = ap.parse_args()

    resultado = extrair(args.arquivo, args.tipo)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
