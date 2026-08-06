/* Painel do representante: aprovar cadastros e mudar o status dos pedidos.
   O acesso é garantido pelo banco (RLS) — esta tela apenas não desenha nada
   para quem não é admin. */

const CFG = window.CONFIG || {};
const $ = (s) => document.querySelector(s);
const estado = { filtro: "" };

const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const dataBR = (iso) => new Date(iso).toLocaleDateString("pt-BR", {
  day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });

async function iniciar() {
  if (CFG.cor) {
    document.documentElement.style.setProperty("--cor", CFG.cor);
    document.documentElement.style.setProperty("--cor-escura", CFG.cor);
  }
  $("#marca-nome").textContent = `Painel — ${CFG.representante || ""}`.trim();

  if (!sistema.ativo) return void ($("#sem-acesso").hidden = false);
  const perfil = await sistema.perfil();
  if (!perfil?.admin) return void ($("#sem-acesso").hidden = false);

  $("#painel").hidden = false;
  $("#btn-sair").hidden = false;
  $("#btn-sair").addEventListener("click", async () => {
    await sistema.sair();
    location.href = "index.html";
  });

  montarFiltros();
  await Promise.all([carregarClientes(), carregarPedidos()]);
}

function montarFiltros() {
  const chips = [["", "Todos"]].concat(
    Object.entries(sistema.STATUS).map(([k, v]) => [k, v.rotulo]));
  $("#filtros-status").innerHTML = chips
    .map(([valor, rotulo]) =>
      `<button type="button" data-status="${valor}"
        aria-current="${valor === estado.filtro}">${rotulo}</button>`)
    .join("");
  $("#filtros-status").onclick = (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    estado.filtro = b.dataset.status;
    montarFiltros();
    carregarPedidos();
  };
}

async function carregarClientes() {
  const alvo = $("#lista-clientes");
  try {
    const pendentes = await sistema.clientes(true);
    $("#n-pendentes").textContent = pendentes.length ? `(${pendentes.length})` : "";
    alvo.innerHTML = pendentes.length
      ? pendentes.map((c) => `
        <div class="cartao linha-cliente" data-id="${c.id}">
          <div>
            <b>${escapar(c.razao_social)}</b>
            <div class="cod">${escapar(c.cnpj)} · ${escapar(c.telefone)}
              ${c.cidade ? `· ${escapar(c.cidade)}/${escapar(c.uf)}` : ""}</div>
            <div class="cod">cadastrado em ${dataBR(c.criado_em)}</div>
          </div>
          <button class="btn-primario" type="button" data-aprovar>Aprovar</button>
        </div>`).join("")
      : '<p class="vazio">Nenhum cadastro aguardando.</p>';
  } catch (e) {
    alvo.innerHTML = `<p class="erro">${escapar(e.message)}</p>`;
  }

  alvo.onclick = async (ev) => {
    const botao = ev.target.closest("[data-aprovar]");
    if (!botao) return;
    const id = botao.closest("[data-id]").dataset.id;
    botao.disabled = true;
    try {
      await sistema.aprovarCliente(id, true);
      await carregarClientes();
    } catch (e) {
      alert(e.message);
      botao.disabled = false;
    }
  };
}

async function carregarPedidos() {
  const alvo = $("#lista-pedidos");
  alvo.innerHTML = '<p class="vazio">Carregando…</p>';
  try {
    const pedidos = await sistema.todosPedidos(estado.filtro || undefined);
    alvo.innerHTML = pedidos.length
      ? pedidos.map(cartaoPedido).join("")
      : '<p class="vazio">Nenhum pedido neste filtro.</p>';
  } catch (e) {
    alvo.innerHTML = `<p class="erro">${escapar(e.message)}</p>`;
    return;
  }

  alvo.onchange = async (ev) => {
    if (!ev.target.matches("[data-status-select]")) return;
    const id = ev.target.closest("[data-id]").dataset.id;
    ev.target.disabled = true;
    try {
      await sistema.mudarStatus(id, ev.target.value);
      await carregarPedidos();
    } catch (e) {
      alert(e.message);
    } finally {
      ev.target.disabled = false;
    }
  };
}

function cartaoPedido(pedido) {
  const cliente = pedido.perfis || {};
  const st = sistema.STATUS[pedido.status] || { cor: "#64748b" };
  const itens = pedido.pedido_itens || [];
  const pecas = itens.reduce((s, i) => s + i.pecas, 0);
  const zap = (cliente.telefone || "").replace(/\D/g, "");
  return `
  <article class="cartao pedido" data-id="${pedido.id}">
    <header class="pedido-topo">
      <div>
        <b>Pedido ${escapar(pedido.numero)}</b>
        <div class="cod">${dataBR(pedido.criado_em)} · ${itens.length} itens · ${pecas} peças</div>
        <div class="cod"><b>${escapar(cliente.razao_social)}</b> · ${escapar(cliente.cnpj)}
          ${zap ? `· <a href="https://wa.me/55${zap}" target="_blank">WhatsApp</a>` : ""}</div>
      </div>
      <div class="acoes-status">
        <b>${formatarBRL(Number(pedido.total))}</b>
        <select data-status-select style="border-color:${st.cor};color:${st.cor}">
          ${Object.entries(sistema.STATUS).map(([k, v]) =>
            `<option value="${k}" ${k === pedido.status ? "selected" : ""}>${v.rotulo}</option>`).join("")}
        </select>
      </div>
    </header>
    <details>
      <summary>Ver itens</summary>
      <table class="tabela">
        <tbody>
          ${itens.map((i) => `<tr>
            <td>${escapar(i.nome)}<div class="cod">${escapar(i.codigo)}</div></td>
            <td class="num">${i.caixas} cx<div class="cod">${i.pecas} pç</div></td>
            <td class="num">${formatarBRL(Number(i.preco_unit))}</td>
            <td class="num"><b>${formatarBRL(Number(i.subtotal))}</b></td>
          </tr>`).join("")}
        </tbody>
      </table>
      ${pedido.observacao ? `<p class="ajuda">Obs.: ${escapar(pedido.observacao)}</p>` : ""}
    </details>
  </article>`;
}

iniciar();
