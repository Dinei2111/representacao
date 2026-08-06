/* Catálogo do representante — site estático, sem dependências.
   Os dados vêm de data/produtos.json; os preços só existem depois que a senha
   decifra assets/precos.enc no navegador. */

const CFG = window.CONFIG || {};
const LOTE = 60;                          // cards renderizados por vez
const CHAVE_PEDIDO = "pedido-knup-v1";

const estado = {
  produtos: [],
  filtrados: [],
  categoria: "",
  busca: "",
  ordem: "catalogo",
  mostrados: 0,
  precos: null,                           // {codigo: {valor, faixas}} depois da senha
  pedido: carregarPedido(),
};

const $ = (sel) => document.querySelector(sel);
const grade = $("#grade");

/* ---------------- utilidades ---------------- */

const semAcento = (t) =>
  t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const paraNumero = (preco) => Number(String(preco).replace(/\./g, "").replace(",", ".")) || 0;

const formatarBRL = (n) =>
  n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

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

function precoDe(codigo) {
  return estado.precos ? estado.precos[codigo] : null;
}

/* ---------------- carga inicial ---------------- */

async function iniciar() {
  aplicarConfig();
  const resp = await fetch("data/produtos.json");
  const dados = await resp.json();
  estado.produtos = dados.produtos.map((p, i) => ({
    ...p,
    ordem: i,
    procura: semAcento([p.nome, p.codigo, p.categoria, p.specs.join(" ")].join(" ")),
  }));

  montarCategorias();
  ligarEventos();
  await tentarSessaoSalva();
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
}

/* ---------------- filtros ---------------- */

function montarCategorias() {
  const contagem = new Map();
  for (const p of estado.produtos) {
    contagem.set(p.categoria, (contagem.get(p.categoria) || 0) + 1);
  }
  const alvo = $("#categorias");
  const linhas = [["", "Todos os produtos", estado.produtos.length]];
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
    estado.categoria = botao.dataset.cat;
    [...alvo.children].forEach((b) => b.setAttribute("aria-current", b === botao));
    filtrar();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
}

function filtrar() {
  const termos = semAcento(estado.busca).split(/\s+/).filter(Boolean);
  let lista = estado.produtos.filter((p) => {
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
  if (!info) return `<div class="preco-oculto">🔒 Preço sob consulta</div>`;
  const extra = (info.faixas || []).find((f) => f.rotulo && f.valor !== info.valor);
  return `<div class="card-preco">${formatarBRL(paraNumero(info.valor))}` +
    (extra ? ` <small>${escapar(extra.rotulo)}: ${formatarBRL(paraNumero(extra.valor))}</small>` : "") +
    `</div>`;
}

function cardHTML(p) {
  const qtd = estado.pedido[p.codigo]?.qtd || 0;
  return `
<article class="card" data-cod="${escapar(p.codigo)}">
  <button class="card-foto" type="button" data-abrir>
    ${p.lancamento ? '<span class="selo">LANÇAMENTO</span>' : ""}
    <img src="${fotoDe(p, true)}" alt="${escapar(p.nome)}" loading="lazy" decoding="async">
  </button>
  <div class="card-info">
    <div class="card-cat">${escapar(p.categoria)}</div>
    <button class="card-nome" type="button" data-abrir>${escapar(p.nome)}</button>
    <div class="card-cod">${escapar(p.codigo)}</div>
    ${blocoPreco(p)}
    <div class="card-rodape">
      ${qtd ? controleQtd(qtd) : '<button class="btn-primario" type="button" data-add>Adicionar</button>'}
    </div>
  </div>
</article>`;
}

function controleQtd(qtd) {
  return `<div class="qtd-mini">
      <button type="button" data-menos aria-label="Diminuir">−</button>
      <input type="number" min="0" value="${qtd}" data-qtd aria-label="Quantidade">
      <button type="button" data-mais aria-label="Aumentar">+</button>
    </div>`;
}

function atualizarCard(codigo) {
  const card = grade.querySelector(`[data-cod="${CSS.escape(codigo)}"] .card-rodape`);
  if (!card) return;
  const qtd = estado.pedido[codigo]?.qtd || 0;
  card.innerHTML = qtd
    ? controleQtd(qtd)
    : '<button class="btn-primario" type="button" data-add>Adicionar</button>';
}

/* ---------------- pedido ---------------- */

function definirQtd(codigo, qtd) {
  qtd = Math.max(0, Math.floor(Number(qtd) || 0));
  if (!qtd) delete estado.pedido[codigo];
  else estado.pedido[codigo] = { qtd };
  salvarPedido();
  atualizarContador();
  atualizarCard(codigo);
  if ($("#pedido").open) desenharPedido();
}

function atualizarContador() {
  const total = Object.values(estado.pedido).reduce((s, i) => s + i.qtd, 0);
  $("#contador").textContent = total;
}

function itensDoPedido() {
  return Object.entries(estado.pedido)
    .map(([codigo, item]) => ({
      produto: estado.produtos.find((p) => p.codigo === codigo),
      qtd: item.qtd,
    }))
    .filter((i) => i.produto);
}

function desenharPedido() {
  const itens = itensDoPedido();
  const corpo = $("#pedido-itens");
  if (!itens.length) {
    corpo.innerHTML = '<p class="vazio">Seu pedido está vazio.<br>Adicione produtos pelo catálogo.</p>';
    $("#pedido-total").textContent = "";
    return;
  }
  corpo.innerHTML = itens.map(({ produto, qtd }) => `
    <div class="item-pedido" data-cod="${escapar(produto.codigo)}">
      <img src="${fotoDe(produto, true)}" alt="" loading="lazy">
      <div>
        <div class="nome">${escapar(produto.nome)}</div>
        <div class="cod">${escapar(produto.codigo)}</div>
        ${controleQtd(qtd)}
      </div>
      <button class="item-remover" type="button" data-remover aria-label="Remover">🗑</button>
    </div>`).join("");

  const total = itens.reduce((s, { produto, qtd }) => {
    const info = precoDe(produto.codigo);
    return s + (info ? paraNumero(info.valor) * qtd : 0);
  }, 0);
  const pecas = itens.reduce((s, i) => s + i.qtd, 0);
  $("#pedido-total").textContent = estado.precos
    ? `${pecas} peças · Total ${formatarBRL(total)}`
    : `${pecas} peças`;
}

function textoDoPedido() {
  const itens = itensDoPedido();
  const nome = $("#cliente-nome").value.trim();
  const cidade = $("#cliente-cidade").value.trim();
  const linhas = [`*Pedido — ${CFG.representante || "catálogo"}*`];
  if (nome) linhas.push(`Cliente: ${nome}`);
  if (cidade) linhas.push(`Cidade: ${cidade}`);
  linhas.push("");
  for (const { produto, qtd } of itens) {
    const info = precoDe(produto.codigo);
    const preco = info ? ` — ${formatarBRL(paraNumero(info.valor))}` : "";
    linhas.push(`${qtd}x ${produto.codigo} — ${produto.nome}${preco}`);
  }
  const pecas = itens.reduce((s, i) => s + i.qtd, 0);
  linhas.push("", `Total de peças: ${pecas}`);
  if (estado.precos) {
    const total = itens.reduce((s, { produto, qtd }) => {
      const info = precoDe(produto.codigo);
      return s + (info ? paraNumero(info.valor) * qtd : 0);
    }, 0);
    linhas.push(`Valor estimado: ${formatarBRL(total)}`);
  }
  if (CFG.tabela) linhas.push(`(${CFG.tabela})`);
  return linhas.join("\n");
}

/* ---------------- ficha do produto ---------------- */

function abrirFicha(codigo) {
  const p = estado.produtos.find((x) => x.codigo === codigo);
  if (!p) return;
  const info = precoDe(p.codigo);
  const faixas = (info?.faixas || []).filter((f) => f.rotulo);
  const qtd = estado.pedido[p.codigo]?.qtd || 0;
  $("#ficha .ficha-conteudo").innerHTML = `
    <div class="ficha-foto"><img src="${fotoDe(p, false)}" alt="${escapar(p.nome)}"></div>
    <div class="ficha-dados">
      <div class="card-cat">${escapar(p.categoria)}</div>
      <h2>${escapar(p.nome)}</h2>
      <div class="meta">
        <span>Código: <b>${escapar(p.codigo)}</b></span>
        ${p.qtd_caixa ? `<span>Caixa com <b>${p.qtd_caixa}</b> un.</span>` : ""}
        ${p.lancamento ? "<span><b>Lançamento</b></span>" : ""}
        <span>Catálogo, pág. <b>${p.pagina}</b></span>
      </div>
      ${info
        ? `<div class="card-preco">${formatarBRL(paraNumero(info.valor))}${
            faixas.length > 1
              ? ` <small>${faixas.slice(1).map((f) =>
                  `${escapar(f.rotulo)}: ${formatarBRL(paraNumero(f.valor))}`).join(" · ")}</small>`
              : ""}</div>`
        : '<div class="preco-oculto">🔒 Preço sob consulta</div>'}
      <ul>${p.specs.map((s) => `<li>${escapar(s)}</li>`).join("")}</ul>
      <div class="acoes-ficha" data-cod="${escapar(p.codigo)}">
        ${qtd ? controleQtd(qtd) : '<button class="btn-primario" type="button" data-add>Adicionar ao pedido</button>'}
      </div>
    </div>`;
  $("#ficha").showModal();
}

/* ---------------- preços com senha ---------------- */

async function derivarChave(senha, salt, iteracoes) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(senha),
    "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: iteracoes, hash: "SHA-256" },
    base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
}

const b64 = (t) => Uint8Array.from(atob(t), (c) => c.charCodeAt(0));

async function abrirPrecos(senha) {
  const pacote = await (await fetch("assets/precos.enc")).json();
  const chave = await derivarChave(senha, b64(pacote.salt), pacote.iter);
  const aberto = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: b64(pacote.nonce) }, chave, b64(pacote.dados));
  return JSON.parse(new TextDecoder().decode(aberto));
}

async function tentarSessaoSalva() {
  const senha = sessionStorage.getItem("senha-tabela");
  if (!senha) return;
  try {
    estado.precos = await abrirPrecos(senha);
    marcarPrecosLiberados();
  } catch {
    sessionStorage.removeItem("senha-tabela");
  }
}

function marcarPrecosLiberados() {
  $("#btn-precos").textContent = "🔓 Preços liberados";
  $("#btn-precos").disabled = true;
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

  // cliques nos cards e nas fichas
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

    if (alvo.closest("[data-add]")) definirQtd(codigo, 1);
    else if (alvo.closest("[data-mais]")) definirQtd(codigo, (estado.pedido[codigo]?.qtd || 0) + 1);
    else if (alvo.closest("[data-menos]")) definirQtd(codigo, (estado.pedido[codigo]?.qtd || 0) - 1);
    else if (alvo.closest("[data-remover]")) definirQtd(codigo, 0);
  });

  document.body.addEventListener("change", (ev) => {
    if (!ev.target.matches("[data-qtd]")) return;
    const codigo = ev.target.closest("[data-cod]")?.dataset.cod;
    if (codigo) definirQtd(codigo, ev.target.value);
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

  $("#enviar-pedido").addEventListener("click", () => {
    if (!itensDoPedido().length) return alert("Adicione produtos ao pedido antes de enviar.");
    const numero = (CFG.whatsapp || "").replace(/\D/g, "");
    if (!numero || /^5*0+$/.test(numero)) {
      return alert("Configure o número de WhatsApp no arquivo config.js.");
    }
    window.open(`https://wa.me/${numero}?text=${encodeURIComponent(textoDoPedido())}`, "_blank");
  });

  $("#btn-precos").addEventListener("click", () => {
    $("#erro-senha").hidden = true;
    $("#senha").showModal();
    $("#campo-senha").focus();
  });

  $("#form-senha").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const senha = $("#campo-senha").value;
    try {
      estado.precos = await abrirPrecos(senha);
      sessionStorage.setItem("senha-tabela", senha);
      marcarPrecosLiberados();
      $("#senha").close();
      $("#campo-senha").value = "";
      filtrar();
      if ($("#pedido").open) desenharPedido();
    } catch {
      $("#erro-senha").hidden = false;
    }
  });

  // rolagem infinita
  new IntersectionObserver((entradas) => {
    if (entradas[0].isIntersecting) renderizarLote();
  }, { rootMargin: "600px" }).observe($("#sentinela"));
}

iniciar();
