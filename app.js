/* Catálogo do representante.
   Os produtos vêm de data/produtos.json (público, sem preço). Os preços vêm do
   banco e só existem para cliente aprovado — ver sistema.js. */

const CFG = window.CONFIG || {};
const LOTE = 60;                          // cards renderizados por vez
const CHAVE_PEDIDO = "pedido-opert-v2";

const estado = {
  produtos: [],
  filtrados: [],
  categoria: "",
  busca: "",
  ordem: "catalogo",
  soPromocao: false,
  mostrados: 0,
  precos: null,                           // {codigo: {de, valor, faixas}}
  perfil: null,
  pedido: carregarPedido(),
};

const $ = (sel) => document.querySelector(sel);
const grade = $("#grade");

const semAcento = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function salvarPedido() {
  localStorage.setItem(CHAVE_PEDIDO, JSON.stringify(estado.pedido));
}

function carregarPedido() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_PEDIDO)) || {};
  } catch {
    return {};
  }
}

const precoDe = (codigo) => (estado.precos ? estado.precos[codigo] : null);
const produtoDe = (codigo) => estado.produtos.find((p) => p.codigo === codigo);

/* ---------------- carga inicial ---------------- */

async function iniciar() {
  aplicarConfig();
  const dados = await (await fetch("data/produtos.json")).json();
  estado.produtos = dados.produtos.map((p, i) => ({
    ...p,
    ordem: i,
    procura: semAcento([p.nome, p.codigo, p.categoria, p.specs.join(" ")].join(" ")),
  }));

  montarCategorias();
  ligarEventos();
  await carregarSessao();
  filtrar();
  atualizarContador();
}

function aplicarConfig() {
  if (CFG.cor) {
    document.documentElement.style.setProperty("--cor", CFG.cor);
    document.documentElement.style.setProperty("--cor-escura", CFG.cor);
  }
  const nome = CFG.representante || "Catálogo de produtos";
  document.title = nome;
  $("#marca-nome").textContent = nome;
  $("#marca-chamada").textContent = CFG.chamada || "";
  $("#rodape-texto").textContent =
    [CFG.regiao, CFG.tabela, CFG.observacao].filter(Boolean).join(" · ");
  if (!sistema.ativo) {
    $("#btn-conta").hidden = true;         // sem banco configurado: só WhatsApp
  }
}

async function carregarSessao() {
  if (!sistema.ativo) return;
  estado.perfil = await sistema.perfil();
  if (estado.perfil?.aprovado) estado.precos = await sistema.precos();
  const botao = $("#btn-conta");
  botao.textContent = estado.perfil
    ? (estado.perfil.admin ? "Painel" : "Minha conta")
    : "Entrar";
  botao.href = estado.perfil?.admin ? "admin.html" : "conta.html";
  if (estado.perfil && !estado.perfil.aprovado) {
    $("#aviso-aprovacao").hidden = false;
  }
}

/* ---------------- filtros ---------------- */

function montarCategorias() {
  const contagem = new Map();
  for (const p of estado.produtos) {
    contagem.set(p.categoria, (contagem.get(p.categoria) || 0) + 1);
  }
  const alvo = $("#categorias");
  const promocoes = estado.produtos.filter((p) => p.promocao).length;
  const linhas = [
    ["", "Todos os produtos", estado.produtos.length],
    ["#promocao", "★ Em promoção", promocoes],
  ];
  for (const [cat, n] of [...contagem].sort((a, b) => a[0].localeCompare(b[0], "pt-BR"))) {
    linhas.push([cat, cat, n]);
  }
  alvo.innerHTML = linhas
    .map(([valor, rotulo, n]) =>
      `<button type="button" data-cat="${escapar(valor)}"
        aria-current="${valor === estado.categoria}">${escapar(rotulo)} <span>${n}</span></button>`)
    .join("");
  alvo.onclick = (ev) => {
    const botao = ev.target.closest("button");
    if (!botao) return;
    const valor = botao.dataset.cat;
    estado.soPromocao = valor === "#promocao";
    estado.categoria = estado.soPromocao ? "" : valor;
    [...alvo.children].forEach((b) => b.setAttribute("aria-current", b === botao));
    filtrar();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
}

function filtrar() {
  const termos = semAcento(estado.busca).split(/\s+/).filter(Boolean);
  let lista = estado.produtos.filter((p) => {
    if (estado.soPromocao && !p.promocao) return false;
    if (estado.categoria && p.categoria !== estado.categoria) return false;
    return termos.every((t) => p.procura.includes(t));
  });

  const valor = (p) => paraNumero(precoDe(p.codigo)?.valor || 0);
  const ordens = {
    catalogo: (a, b) => a.ordem - b.ordem,
    nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR"),
    "preco-asc": (a, b) => valor(a) - valor(b) || a.ordem - b.ordem,
    "preco-desc": (a, b) => valor(b) - valor(a) || a.ordem - b.ordem,
  };
  lista = lista.sort(ordens[estado.ordem] || ordens.catalogo);

  estado.filtrados = lista;
  estado.mostrados = 0;
  grade.innerHTML = "";
  $("#vazio").hidden = lista.length > 0;
  $("#resumo").textContent = `${lista.length} produto${lista.length === 1 ? "" : "s"}` +
    (estado.soPromocao ? " em promoção" : "") +
    (estado.categoria ? ` em ${estado.categoria}` : "") +
    (estado.busca ? ` para “${estado.busca}”` : "");
  renderizarLote();
}

function renderizarLote() {
  const fatia = estado.filtrados.slice(estado.mostrados, estado.mostrados + LOTE);
  if (!fatia.length) return;
  grade.insertAdjacentHTML("beforeend", fatia.map(cardHTML).join(""));
  estado.mostrados += fatia.length;
}

/* ---------------- cards ---------------- */

function escapar(t) {
  return String(t).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fotoDe(p, thumb) {
  return p.imagens.length
    ? `assets/produtos/${p.imagens[0]}${thumb ? "-t" : ""}.webp`
    : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E";
}

function blocoPreco(p) {
  const info = precoDe(p.codigo);
  if (!info) {
    return p.promocao
      ? '<div class="preco-oculto">🔒 Preço promocional sob consulta</div>'
      : '<div class="preco-oculto">🔒 Preço sob consulta</div>';
  }
  const faixas = textoDasFaixas(info);
  return `<div class="card-preco">
      ${temPromocao(info) ? `<s>${formatarBRL(paraNumero(info.de))}</s> ` : ""}
      ${formatarBRL(paraNumero(info.valor))}
      <small>por peça</small>
    </div>${faixas ? `<div class="faixas">${escapar(faixas)}</div>` : ""}`;
}

/** "1 cx = 100 peças" — a Knup só vende caixa fechada. */
function textoCaixa(p, caixas = 1) {
  if (!p.qtd_caixa) return `${caixas} un. · quantidade a confirmar`;
  return `${caixas} cx = ${pecasDe(p, caixas)} peças`;
}

function cardHTML(p) {
  const caixas = estado.pedido[p.codigo]?.caixas || 0;
  const info = precoDe(p.codigo);
  const desconto = descontoPercentual(info);
  return `
<article class="card" data-cod="${escapar(p.codigo)}">
  <button class="card-foto" type="button" data-abrir>
    ${p.promocao ? `<span class="selo selo-promo">PROMOÇÃO${desconto ? ` −${desconto}%` : ""}</span>`
                 : (p.lancamento ? '<span class="selo">LANÇAMENTO</span>' : "")}
    <img src="${fotoDe(p, true)}" alt="${escapar(p.nome)}" loading="lazy" decoding="async">
  </button>
  <div class="card-info">
    <div class="card-cat">${escapar(p.categoria)}</div>
    <button class="card-nome" type="button" data-abrir>${escapar(p.nome)}</button>
    <div class="card-cod">${escapar(p.codigo)}</div>
    <div class="card-caixa">${escapar(textoCaixa(p))}</div>
    ${blocoPreco(p)}
    <div class="card-rodape">
      ${caixas ? controleQtd(caixas) : '<button class="btn-primario" type="button" data-add>Adicionar</button>'}
    </div>
  </div>
</article>`;
}

function controleQtd(caixas) {
  return `<div class="qtd-mini" title="quantidade em caixas fechadas">
      <button type="button" data-menos aria-label="Menos uma caixa">−</button>
      <input type="number" min="0" value="${caixas}" data-qtd aria-label="Caixas">
      <button type="button" data-mais aria-label="Mais uma caixa">+</button>
      <span class="un">cx</span>
    </div>`;
}

function atualizarCard(codigo) {
  for (const alvo of grade.querySelectorAll(`[data-cod="${CSS.escape(codigo)}"] .card-rodape`)) {
    const caixas = estado.pedido[codigo]?.caixas || 0;
    alvo.innerHTML = caixas
      ? controleQtd(caixas)
      : '<button class="btn-primario" type="button" data-add>Adicionar</button>';
  }
}

/* ---------------- pedido ---------------- */

function definirCaixas(codigo, caixas) {
  caixas = Math.max(0, Math.floor(Number(caixas) || 0));
  if (!caixas) delete estado.pedido[codigo];
  else estado.pedido[codigo] = { caixas };
  salvarPedido();
  atualizarContador();
  atualizarCard(codigo);
  if ($("#pedido").open) desenharPedido();
  if ($("#ficha").open) {
    const acoes = $("#ficha .acoes-ficha");
    if (acoes?.dataset.cod === codigo) {
      acoes.innerHTML = caixas
        ? controleQtd(caixas)
        : '<button class="btn-primario" type="button" data-add>Adicionar ao pedido</button>';
    }
  }
}

function atualizarContador() {
  $("#contador").textContent = Object.values(estado.pedido)
    .reduce((s, i) => s + i.caixas, 0);
}

/** Itens do pedido já com peças, preço aplicado e subtotal. */
function itensDoPedido() {
  return Object.entries(estado.pedido)
    .map(([codigo, item]) => {
      const produto = produtoDe(codigo);
      if (!produto) return null;
      const info = precoDe(codigo);
      const unit = precoUnitario(info, produto, item.caixas);
      const pecas = pecasDe(produto, item.caixas);
      return { produto, caixas: item.caixas, pecas, unit, subtotal: unit * pecas };
    })
    .filter(Boolean);
}

function desenharPedido() {
  const itens = itensDoPedido();
  const corpo = $("#pedido-itens");
  if (!itens.length) {
    corpo.innerHTML = '<p class="vazio">Seu pedido está vazio.<br>Adicione produtos pelo catálogo.</p>';
    $("#pedido-total").textContent = "";
    return;
  }
  corpo.innerHTML = itens.map(({ produto, caixas, pecas, unit, subtotal }) => `
    <div class="item-pedido" data-cod="${escapar(produto.codigo)}">
      <img src="${fotoDe(produto, true)}" alt="" loading="lazy">
      <div>
        <div class="nome">${escapar(produto.nome)}</div>
        <div class="cod">${escapar(produto.codigo)} · ${escapar(textoCaixa(produto, caixas))}</div>
        ${controleQtd(caixas)}
        ${unit ? `<div class="sub">${pecas} × ${formatarBRL(unit)} =
                  <b>${formatarBRL(subtotal)}</b></div>` : ""}
      </div>
      <button class="item-remover" type="button" data-remover aria-label="Remover">🗑</button>
    </div>`).join("");

  const totalCaixas = itens.reduce((s, i) => s + i.caixas, 0);
  const totalPecas = itens.reduce((s, i) => s + i.pecas, 0);
  const total = itens.reduce((s, i) => s + i.subtotal, 0);
  $("#pedido-total").innerHTML = `${totalCaixas} caixas · ${totalPecas} peças` +
    (estado.precos ? ` · <b>${formatarBRL(total)}</b>` : "");
}

function textoDoPedido(numero) {
  const itens = itensDoPedido();
  const linhas = [`*Pedido${numero ? ` ${numero}` : ""} — ${CFG.representante || "catálogo"}*`];
  if (estado.perfil) linhas.push(`Cliente: ${estado.perfil.razao_social} (${estado.perfil.cnpj})`);
  linhas.push("");
  for (const { produto, caixas, pecas, unit } of itens) {
    const preco = unit ? ` — ${formatarBRL(unit)}/pç` : "";
    linhas.push(`${caixas} cx (${pecas} pç) ${produto.codigo} — ${produto.nome}${preco}`);
  }
  const total = itens.reduce((s, i) => s + i.subtotal, 0);
  linhas.push("", `Total: ${itens.reduce((s, i) => s + i.pecas, 0)} peças`);
  if (estado.precos) linhas.push(`Valor: ${formatarBRL(total)}`);
  if (CFG.observacao) linhas.push(CFG.observacao);
  return linhas.join("\n");
}

function linkWhatsApp(texto) {
  const numero = (CFG.whatsapp || "").replace(/\D/g, "");
  if (!numero || /^5*0+$/.test(numero)) return null;
  return `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`;
}

function abrirWhatsApp(texto) {
  const link = linkWhatsApp(texto);
  if (!link) return alert("Configure o número de WhatsApp no arquivo config.js.");
  window.open(link, "_blank");
}

/** Concluir: sem conta vai para o cadastro; com conta grava e avisa no WhatsApp. */
async function concluirPedido() {
  const itens = itensDoPedido();
  if (!itens.length) return alert("Adicione produtos ao pedido antes de concluir.");

  if (!sistema.ativo) {                    // catálogo sem banco: só WhatsApp
    abrirWhatsApp(textoDoPedido());
    return;
  }
  if (!estado.perfil) {
    sessionStorage.setItem("voltar-para", "pedido");
    window.location.href = "conta.html?motivo=pedido";
    return;
  }
  if (!estado.perfil.aprovado) {
    alert("Seu cadastro ainda está em análise. Assim que for aprovado você consegue fechar o pedido.");
    return;
  }

  const botao = $("#concluir-pedido");
  botao.disabled = true;
  botao.textContent = "Enviando…";
  try {
    const pedido = await sistema.criarPedido(
      itens.map((i) => ({
        codigo: i.produto.codigo, nome: i.produto.nome, caixas: i.caixas,
        pecas: i.pecas, preco_unit: i.unit, subtotal: i.subtotal,
      })),
      $("#pedido-observacao").value.trim() || null);

    // o texto tem que ser montado antes de esvaziar a lista
    const aviso = textoDoPedido(pedido.numero);
    const totalPecas = itens.reduce((s, i) => s + i.pecas, 0);
    const total = itens.reduce((s, i) => s + i.subtotal, 0);

    estado.pedido = {};
    salvarPedido();
    atualizarContador();
    $("#pedido").close();
    filtrar();
    mostrarConfirmacao(pedido, itens.length, totalPecas, total, aviso);
  } catch (erro) {
    alert(erro.message);
  } finally {
    botao.disabled = false;
    botao.textContent = "Concluir pedido";
  }
}

/** Tela de "pedido registrado". O aviso no WhatsApp fica num botão porque o
    navegador bloqueia abrir aba sozinho depois de uma gravação. */
function mostrarConfirmacao(pedido, itens, pecas, total, aviso) {
  const link = linkWhatsApp(aviso);
  $("#confirmacao-conteudo").innerHTML = `
    <h2>Pedido ${escapar(pedido.numero)} registrado ✓</h2>
    <p class="ajuda">${itens} ${itens === 1 ? "item" : "itens"} · ${pecas} peças
      ${estado.precos ? `· <b>${formatarBRL(total)}</b>` : ""}<br>
      Status inicial: <b>pendente</b>. Acompanhe em “Minha conta”.</p>
    <p class="ajuda">Avise no WhatsApp para agilizarmos a separação e o pagamento.</p>
    <div class="painel-botoes">
      <a class="btn-secundario" href="conta.html">Ver meus pedidos</a>
      ${link ? `<a class="btn-whats" href="${link}" target="_blank" rel="noopener"
                  id="link-whats">Avisar no WhatsApp</a>` : ""}
    </div>`;
  $("#confirmacao").showModal();
}

/* ---------------- ficha do produto ---------------- */

function abrirFicha(codigo) {
  const p = produtoDe(codigo);
  if (!p) return;
  const info = precoDe(p.codigo);
  const caixas = estado.pedido[p.codigo]?.caixas || 0;
  const faixas = textoDasFaixas(info);
  $("#ficha .ficha-conteudo").innerHTML = `
    <div class="ficha-foto"><img src="${fotoDe(p, false)}" alt="${escapar(p.nome)}"></div>
    <div class="ficha-dados">
      <div class="card-cat">${escapar(p.categoria)}</div>
      <h2>${escapar(p.nome)}</h2>
      <div class="meta">
        <span>Código: <b>${escapar(p.codigo)}</b></span>
        ${p.qtd_caixa ? `<span>Caixa fechada: <b>${p.qtd_caixa}</b> peças</span>`
                      : "<span>Quantidade por caixa a confirmar</span>"}
        ${p.promocao ? "<span><b>Promoção</b></span>" : ""}
        ${p.lancamento ? "<span><b>Lançamento</b></span>" : ""}
        <span>Catálogo, pág. <b>${p.pagina}</b></span>
      </div>
      ${blocoPreco(p)}
      ${faixas ? "" : ""}
      <ul>${p.specs.map((s) => `<li>${escapar(s)}</li>`).join("")}</ul>
      <div class="acoes-ficha" data-cod="${escapar(p.codigo)}">
        ${caixas ? controleQtd(caixas)
                 : '<button class="btn-primario" type="button" data-add>Adicionar ao pedido</button>'}
      </div>
    </div>`;
  $("#ficha").showModal();
}

/* ---------------- eventos ---------------- */

function ligarEventos() {
  $("#busca").addEventListener("input", (ev) => {
    estado.busca = ev.target.value.trim();
    clearTimeout(ligarEventos._t);
    ligarEventos._t = setTimeout(filtrar, 140);
  });

  $("#ordem").addEventListener("change", (ev) => {
    estado.ordem = ev.target.value;
    filtrar();
  });

  document.body.addEventListener("click", (ev) => {
    const alvo = ev.target;
    if (alvo.closest("[data-fechar]")) {
      alvo.closest("dialog").close();
      return;
    }
    const contexto = alvo.closest("[data-cod]");
    const codigo = contexto?.dataset.cod;
    if (alvo.closest("[data-abrir]") && codigo) return abrirFicha(codigo);
    if (!codigo) return;

    const atual = estado.pedido[codigo]?.caixas || 0;
    if (alvo.closest("[data-add]")) definirCaixas(codigo, 1);
    else if (alvo.closest("[data-mais]")) definirCaixas(codigo, atual + 1);
    else if (alvo.closest("[data-menos]")) definirCaixas(codigo, atual - 1);
    else if (alvo.closest("[data-remover]")) definirCaixas(codigo, 0);
  });

  document.body.addEventListener("change", (ev) => {
    if (!ev.target.matches("[data-qtd]")) return;
    const codigo = ev.target.closest("[data-cod]")?.dataset.cod;
    if (codigo) definirCaixas(codigo, ev.target.value);
  });

  $("#btn-pedido").addEventListener("click", () => {
    desenharPedido();
    $("#pedido").showModal();
  });

  $("#limpar-pedido").addEventListener("click", () => {
    if (!confirm("Remover todos os itens do pedido?")) return;
    for (const codigo of Object.keys(estado.pedido)) {
      delete estado.pedido[codigo];
      atualizarCard(codigo);
    }
    salvarPedido();
    atualizarContador();
    desenharPedido();
  });

  $("#concluir-pedido").addEventListener("click", concluirPedido);

  new IntersectionObserver((entradas) => {
    if (entradas[0].isIntersecting) renderizarLote();
  }, { rootMargin: "600px" }).observe($("#sentinela"));

  // veio da tela de conta depois de entrar: reabre o pedido
  if (sessionStorage.getItem("voltar-para") === "pedido") {
    sessionStorage.removeItem("voltar-para");
    setTimeout(() => { desenharPedido(); $("#pedido").showModal(); }, 300);
  }
}

iniciar();
