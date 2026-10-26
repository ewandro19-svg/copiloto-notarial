# Correções do modelo de Compra e Venda — prontas pra aplicar

Use Ctrl+H (Localizar e Substituir) no Word pra cada item. Todos foram
confirmados contra uma geração real do seu sistema (`minuta_gerada__4_.docx`).

---

## 1 — Item 7: falta a cláusula de exceção de ônus

**Buscar:**
```
possuidores da ...............?...........totalidade DO IMÓVEL ora vendido, o qual está livre e desembaraçado de quaisquer ônus, ações fundadas em direito real e pessoal ou reipersecutória.
```

**Substituir por:**
```
possuidores da totalidade DO IMÓVEL ora vendido, o qual está livre e desembaraçado de quaisquer ônus, ações fundadas em direito real e pessoal ou reipersecutória«<CITAR_ONUS_(SE_HOUVER)>».
```

---

## 2 — Item 11-a: vírgula dobrada

**Buscar:**
```
93.240/86), , à exceção
```

**Substituir por:**
```
93.240/86), à exceção
```

---

## 3 — Item 9: frase de quitação duplicada (mantendo só a versão sem nomes)

**Buscar:**
```
de titularidade de SIDNEY MARZOLA e MARIA FERRAZ DE VASCONCELOS MARZOLA, pelo qual SIDNEY MARZOLA e MARIA FERRAZ DE VASCONCELOS MARZOLA dão plena, geral e irrevogável quitação , pelo qual OS OUTORGANTES VENDEDORES dão plena, geral e irrevogável quitação.
```

**Substituir por:**
```
de titularidade de SIDNEY MARZOLA e MARIA FERRAZ DE VASCONCELOS MARZOLA, pelo qual OS OUTORGANTES VENDEDORES dão plena, geral e irrevogável quitação.
```

> Atenção: os nomes "SIDNEY MARZOLA e MARIA FERRAZ..." nesse trecho são
> gerados dinamicamente (tags de nome), então o texto de busca acima só
> vai bater exatamente numa geração com essas duas pessoas. Se não
> achar esse texto exato ao buscar, procure manualmente pelo padrão
> "dão plena, geral e irrevogável quitação" repetido duas vezes seguidas
> no item 9, e apague a primeira ocorrência (a que cita os nomes),
> mantendo só a segunda (a que diz "OS OUTORGANTES VENDEDORES").

---

## 4 — Item 11-c: remover a nota de revisão (a cláusula em si fica, sempre)

**Buscar:**
```
VERIFICAR CABIMENTO DECL. DE CONDOMINIO ACIMA (SE NÃO, EXCLUIR)...
```

**Substituir por:** (vazio — apagar essa linha inteira)

---

## 5 — Item 14-e: remover texto solto

**Buscar:**
```
válidas por 30 (trinta) dias da data de expedição;DATA CERTIDAO JUSTIÇA DO TRABALH O
```

**Substituir por:**
```
válidas por 30 (trinta) dias da data de expedição;
```

---

## 6 — Final: remover nota "QUALIFICAR A ROGO"

**Buscar:**
```
a presente será registrada junto ao Distribuidor competenteQUALIFICAR A ROGO.,
```

**Substituir por:**
```
a presente será registrada junto ao Distribuidor competente,
```

(Repara que isso já resolve de quebra o espaço faltando depois de "competente".)

---

## 7 — Espaços faltando (itens 6, 15, 16, 17)

| Buscar | Substituir por |
|---|---|
| `6-DO TÍTULO AQUISITIVO:Imóvel` | `6-DO TÍTULO AQUISITIVO: Imóvel` |
| `15-DO REQUERIMENTO:As partes` | `15-DO REQUERIMENTO: As partes` |
| `16-DA EMISSÃO DA DOI:Foi emitida` | `16-DA EMISSÃO DA DOI: Foi emitida` |
| `17-DA CLÁUSULA MANDATO:Pelos` | `17-DA CLÁUSULA MANDATO: Pelos` |

---

## 8 — Item 14 (b, e, f, g, h): juntar os números do outorgante + cônjuge

Isso é a correção mais importante e também a mais delicada — precisa trocar
o **marcador** de cada alínea, não só o texto visível. Procure por cada uma
dessas 5 tags (são invisíveis no texto normal, mas aparecem se você ativar
"Mostrar tudo" ou olhar os campos — no seu sistema, geralmente ficam coladas
logo depois da letra da alínea):

| Tipo | Buscar | Substituir por |
|---|---|---|
| b) Débitos Trabalhistas | `«CERTIDAO:debitos_trabalhistas»` | `«CERTIDAO:ambos:debitos_trabalhistas»` |
| e) Ações Trabalhistas | `«CERTIDAO:feitos_trt»` | `«CERTIDAO:ambos:feitos_trt»` |
| f) Distribuição Cíveis | `«CERTIDAO:feitos_trf»` | `«CERTIDAO:ambos:feitos_trf»` |
| g) Tributos Federais | `«CERTIDAO:tributos_federais»` | `«CERTIDAO:ambos:tributos_federais»` |
| h) Tributos Estaduais | `«CERTIDAO:tributos_estaduais»` | `«CERTIDAO:ambos:tributos_estaduais»` |

**Isso só funciona depois que você aplicar o `.zip` do projeto atualizado**
(o modo `ambos` é código novo que construí e testei nesta conversa — sem o
código novo, essa tag não existe e o parágrafo ficaria sem alteração).

---

## 9 — Item 14-c: certidão sem marcador nenhum (em branco)

Essa alínea (1º Distribuidor) parece não ter nenhum marcador `«CERTIDAO:...»`
hoje — por isso sai sempre em branco. Se você quiser que ela funcione
igual as outras, a redação precisa ficar parecida com o padrão das demais,
com o marcador no começo. Me manda o texto bruto dessa alínea (ou o
arquivo) que eu te dou o texto exato — não tenho certeza suficiente do
que já existe aí pra te dar a substituição sem ver.

---

## Pendente (preciso ver o texto bruto do seu arquivo pra confirmar)

- **Item 4**: os pontinhos (`da \...\.....???\...\...\.....um imóvel`)
  provavelmente deveriam usar a variável `«<FRACAO_VENDIDA>»` que já
  existe no sistema (totalidade vs. fração ideal), mas preciso ver se
  essa tag já está em algum lugar próximo antes de confirmar — se não
  tiver nada, a correção mais simples é só apagar os pontinhos, ficando
  "da totalidade de um imóvel".
- **Item 9**: o trecho "recebido da COMPRADORA `...?...`neste ato`....?...`por
  meio de **em** moeda corrente" está com uma palavra sobrando ("de" antes
  de "em") e pontinhos soltos — preciso ver o texto bruto (com as tags)
  pra saber exatamente o que deveria estar ali.

Pra esses 2 últimos, se puder me mandar o `.docx` de verdade (não só a
minuta gerada), eu resolvo na hora.
