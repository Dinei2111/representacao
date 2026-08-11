# Opert Representações — catálogo e pedidos

Site do representante com os catálogos da **Knup** (821 produtos, tabela à vista de
03/08/2026) e da **Onistek** (451 produtos, tabela à vista de 10/08/2026), usando as
mesmas fotos e descrições dos catálogos oficiais. Um bloco no topo do site deixa o
cliente escolher o fornecedor — cada um com suas próprias categorias, fotos e preços,
sem misturar. O cliente se cadastra, monta o pedido em caixas fechadas e acompanha o
status; você muda o status pelo painel.

- **Bloco de fornecedor** no topo — cada fornecedor com seu próprio catálogo e categorias
- Catálogo público **sem preço**; preços liberados por **cliente aprovado**
- **Promoções** do catálogo (de/por) e **preço por volume** (3 cx, 5 cx, 50 pçs)
- Venda em **caixa fechada**, como manda a política de cada fornecedor
- Pedido salvo no sistema com status: pendente → pago → faturado → enviado → entregue
- Site estático no GitHub Pages + banco no Supabase — os dois no plano gratuito

## Como colocar no ar

### 1. Publicar o site (5 minutos)
No GitHub: **Settings → Pages → Deploy from a branch → `main` / `(root)` → Save**.
Em um ou dois minutos o site fica em `https://dinei2111.github.io/representacao/`.

Nesse ponto o site já funciona como catálogo com pedido por WhatsApp. Os preços e a
área de conta só aparecem depois do passo 2.

### 2. Ligar o sistema de pedidos (15 minutos)

1. Crie uma conta grátis em [supabase.com](https://supabase.com) e um projeto
   (região **South America (São Paulo)**).
2. No menu **SQL Editor**, cole e execute, nesta ordem:
   - `supabase/schema.sql` — cria as tabelas e as regras de acesso
   - `supabase/precos.sql` — carrega os preços da Knup
   - `supabase/precos-onistek.sql` — carrega os preços da Onistek
3. Em **Authentication → Sign In / Providers → Email**, desligue **"Confirm email"**.
   Quem libera o acesso é você, pelo painel — não precisa confirmar e-mail.
4. Em **Settings → API**, copie **Project URL** e a chave **anon public** para o
   `config.js`:

   ```js
   supabaseUrl: "https://xxxxxxxx.supabase.co",
   supabaseAnonKey: "eyJhbGci...",
   ```

   A `anon key` é pública por natureza — quem protege os dados são as regras de acesso
   do banco (RLS), já testadas: cliente só vê o próprio pedido, preço só sai para
   aprovado, e ninguém se aprova sozinho.
5. Entre no site, crie **sua** conta em "Entrar → Criar cadastro" e depois rode no
   SQL Editor, trocando o e-mail:

   ```sql
   update public.perfis set admin = true, aprovado = true
    where id = (select id from auth.users where email = 'seu-email@exemplo.com');
   ```

6. Pronto: `admin.html` é o seu painel (aprovar cadastros e mudar status) e
   `conta.html` é a área do cliente.

## O dia a dia

| Situação | O que acontece |
|---|---|
| Cliente novo se cadastra | Entra como "em análise" e pode te chamar no WhatsApp por um botão |
| Você aprova no painel | Os preços passam a aparecer para ele |
| Cliente fecha o pedido | Nasce como **pendente**, com número (`2026-0001`), e ele te avisa no WhatsApp |
| Você recebe o pagamento | Muda para **pago** no painel; o cliente vê na hora em "Meus pedidos" |
| Faturou / enviou / entregou | Mesma coisa — cada mudança fica registrada com data |

## Atualizar o catálogo quando sair tabela nova

**Knup:**

```bash
cp /caminho/da/nova/tabela.pdf catalogo/Knup_A_Vista_03082026.pdf
pip install pymupdf pillow
python3 tools/extract_catalog.py     # relê o PDF: produtos, fotos e preços
python3 tools/sync_supabase.py       # gera supabase/precos.sql
python3 tools/qa_report.py           # conferência: abra build/qa.html
git add -A && git commit -m "atualiza catálogo Knup" && git push
```

**Onistek:**

```bash
cp /caminho/da/nova/tabela.pdf catalogo/Onistek_A_Vista_10082026.pdf
python3 tools/extract_catalog_onistek.py   # relê o PDF: produtos, fotos e preços
python3 tools/sync_supabase.py onistek     # gera supabase/precos-onistek.sql
python3 tools/qa_report.py onistek         # conferência: abra build/qa-onistek.html
git add -A && git commit -m "atualiza catálogo Onistek" && git push
```

Depois cole o `.sql` novo no SQL Editor (cada fornecedor só apaga e recarrega as
próprias linhas — não mexe nas do outro). Se o arquivo do PDF mudar de nome, ajuste a
constante `PDF` no extrator correspondente e a data em `config.js`.

**Cada fornecedor tem seu próprio extrator** porque o layout do PDF é diferente
(colunas, faixas de preço, cabeçalho de categoria). Para adicionar um fornecedor novo,
copie `tools/extract_catalog_onistek.py` como ponto de partida, ajuste `PDF`,
`FORNECEDOR` e os detalhes de layout, gere `data/produtos-<fornecedor>.json` e inclua o
arquivo na lista `CATALOGOS` de `app.js`.

**O extrator avisa quando algo não fecha** (produto sem preço, preço sem dono, quadro
esticado). Se aparecer algum aviso, confira a página no `build/qa.html` (ou
`build/qa-onistek.html`) antes de publicar.

## Conferência

```bash
python3 tools/extract_catalog.py         # Knup: 821 produtos, 0 avisos
python3 tools/extract_catalog_onistek.py # Onistek: 451 produtos, 1 aviso (KP-491 sem
                                          # preço no PDF original)
python3 tools/qa_report.py               # build/qa.html: PDF Knup ao lado do extraído
python3 tools/qa_report.py onistek       # build/qa-onistek.html: idem, PDF Onistek
python3 -m http.server 8000              # site em http://localhost:8000
```

As regras de segurança do banco têm teste próprio, para rodar num Postgres local:

```bash
psql -f supabase/testes.sql          # 17 verificações de quem pode ver/fazer o quê
```

## Estrutura

```
index.html  app.js  precos.js        catálogo, pedido e regras de preço
conta.html  conta.js                 cadastro, login e "Meus pedidos"
admin.html  admin.js                 painel: aprovar clientes, mudar status
sistema.js                           acesso ao banco (Supabase)
politica.html                        política comercial (pág. final de cada catálogo)
config.js                            seus dados: nome, WhatsApp, cor, chaves do Supabase
styles.css                           estilo de todas as telas
data/produtos.json                   821 produtos da Knup, sem preços
data/produtos-onistek.json           451 produtos da Onistek, sem preços
assets/produtos/*.webp               fotos da Knup (grande + miniatura -t)
assets/produtos/onistek/*.webp       fotos da Onistek (grande + miniatura -t)
assets/vendor/supabase.js            biblioteca do Supabase (sem CDN)
supabase/schema.sql                  tabelas, regras de acesso e histórico de status
supabase/precos.sql                  preços da Knup gerados do PDF
supabase/precos-onistek.sql          preços da Onistek gerados do PDF
supabase/testes.sql                  testes das regras de acesso
tools/extract_catalog.py             PDF Knup → produtos, fotos e preços
tools/extract_catalog_onistek.py     PDF Onistek → produtos, fotos e preços
tools/sync_supabase.py               preços → SQL (knup ou onistek)
tools/qa_report.py                   relatório de conferência (knup ou onistek)
catalogo/*.pdf                       PDFs de origem
```

## Custos

GitHub Pages e Supabase são gratuitos nas faixas usadas aqui (o plano free do Supabase
cobre 50 mil usuários e 500 MB de banco — muito acima do que este catálogo consome).
Projetos gratuitos do Supabase hibernam depois de uma semana sem acesso; basta abrir o
painel para religar.

---

As imagens e descrições pertencem a cada fabricante (Knup, Onistek) e são reproduzidas
para divulgação da representação. Se o fabricante exigir aprovação prévia do material,
confirme antes de divulgar o site.
