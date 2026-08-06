# Catálogo do representante

Site estático com os **787 produtos** do catálogo Knup (tabela à vista de 03/08/2026),
com as mesmas fotos e descrições do PDF original. O cliente navega, busca, monta uma
lista de itens e envia o pedido pronto pelo WhatsApp.

- Catálogo público, **sem preços**
- Tabela de preços liberada por **senha** (os preços são publicados criptografados)
- Pedido montado no site e enviado pelo WhatsApp já formatado com os códigos
- Sem servidor e sem custo: roda no GitHub Pages

## Como publicar (uma vez só)

1. No GitHub, abra **Settings → Pages**
2. Em *Source*, escolha **Deploy from a branch**
3. Branch: `main` · pasta: `/ (root)` · **Save**
4. Em um ou dois minutos o site fica no ar em
   `https://dinei2111.github.io/representacao/`

## O que você precisa preencher

Abra `config.js` e troque os valores:

```js
representante: "Seu nome / sua empresa",
whatsapp: "5541999999999",   // 55 + DDD + número, só dígitos
regiao: "Atendimento a lojistas no Paraná",
```

E defina a senha da tabela de preços (veja abaixo). **Sem isso o botão de WhatsApp
avisa que falta configurar o número.**

## Senha da tabela de preços

Os preços não ficam escondidos com CSS — eles são publicados **criptografados**
(AES-256-GCM, chave derivada da senha com PBKDF2/250 mil iterações). Quem não tem a
senha não consegue lê-los nem olhando o código-fonte da página.

Para trocar a senha:

```bash
python3 tools/extract_catalog.py            # gera build/precos.json
python3 tools/encrypt_prices.py --senha "sua-nova-senha"
git add assets/precos.enc && git commit -m "atualiza senha da tabela" && git push
```

A senha nunca entra no repositório — só o arquivo cifrado `assets/precos.enc`.

## Atualizar o catálogo quando sair uma tabela nova

```bash
cp /caminho/da/nova/tabela.pdf catalogo/Knup_A_Vista_03082026.pdf
pip install pymupdf pillow cryptography
python3 tools/extract_catalog.py            # relê o PDF: JSON + fotos WebP
python3 tools/encrypt_prices.py --senha "sua-senha"
python3 tools/qa_report.py                  # confere: abra build/qa.html
git add -A && git commit -m "atualiza catálogo" && git push
```

Se o nome do arquivo mudar, ajuste a constante `PDF` em `tools/extract_catalog.py`
e a data em `config.js` (`tabela`).

## Estrutura

```
index.html  app.js  styles.css     o site
config.js                          seus dados (nome, WhatsApp, cor)
data/produtos.json                 787 produtos, sem preços
assets/produtos/*.webp             fotos (grande + miniatura -t)
assets/precos.enc                  tabela de preços criptografada
catalogo/*.pdf                     PDF de origem
tools/extract_catalog.py           PDF  -> JSON + fotos
tools/encrypt_prices.py            preços -> arquivo criptografado
tools/qa_report.py                 relatório de conferência (build/qa.html)
```

## Rodar localmente

```bash
python3 -m http.server 8000
# abra http://localhost:8000
```

## Conferência da extração

`python3 tools/qa_report.py` gera `build/qa.html` com **cada página do PDF renderizada
ao lado dos produtos extraídos dela** — é o jeito de conferir nome, descrição, código,
preço e foto item a item depois de reprocessar o catálogo.

---

As imagens e descrições pertencem ao fabricante e são reproduzidas aqui para divulgação
da representação. Se o fabricante exigir aprovação prévia do material de divulgação,
confirme com ele antes de tornar o site público.
