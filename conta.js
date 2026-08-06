/* Tela do cliente: entrar, criar cadastro e acompanhar os pedidos. */

const CFG = window.CONFIG || {};
const $ = (s) => document.querySelector(s);

const escapar = (t) => String(t).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const dataBR = (iso) => new Date(iso).toLocaleDateString("pt-BR", {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

function aplicarConfig() {
  if (CFG.cor) {
    document.documentElement.style.setProperty("--cor", CFG.cor);
    document.documentElement.style.setProperty("--cor-escura", CFG.cor);
  }
  $("#marca-nome").textContent = CFG.representante || "Minha conta";
  $("#marca-chamada").textContent = "Meus pedidos e cadastro";
  document.title = `Minha conta — ${CFG.representante || ""}`.trim();
}

async function iniciar() {
  aplicarConfig();
  if (!sistema.ativo) {
    $("#sem-sistema").hidden = false;
    return;
  }
  ligarEventos();
  const perfil = await sistema.perfil();
  if (perfil) mostrarPedidos(perfil);
  else mostrarAcesso();
}

function mostrarAcesso() {
  $("#area-acesso").hidden = false;
  $("#area-pedidos").hidden = true;
  $("#btn-sair").hidden = true;
  const motivo = new URLSearchParams(location.search).get("motivo");
  if (motivo === "pedido") {
    const aviso = $("#motivo");
    aviso.textContent = "Para concluir o pedido, entre na sua conta ou faça o cadastro.";
    aviso.hidden = false;
  }
}

async function mostrarPedidos(perfil) {
  $("#area-acesso").hidden = true;
  $("#area-pedidos").hidden = false;
  $("#btn-sair").hidden = false;

  $("#cartao-perfil").innerHTML = `
    <h2>${escapar(perfil.razao_social)}</h2>
    <div class="meta">
      <span>CNPJ: <b>${escapar(perfil.cnpj)}</b></span>
      <span>${escapar(perfil.email || "")}</span>
      ${perfil.cidade ? `<span>${escapar(perfil.cidade)}/${escapar(perfil.uf || "")}</span>` : ""}
    </div>
    <p class="${perfil.aprovado ? "sucesso" : "aviso-inline"}">
      ${perfil.aprovado
        ? "✓ Cadastro aprovado — preços liberados no catálogo."
        : "⏳ Cadastro em análise. Assim que for aprovado, os preços aparecem no catálogo."}
    </p>
    ${!perfil.aprovado && linkLiberacao(perfil)
      ? `<p><a class="btn-whats" href="${linkLiberacao(perfil)}" target="_blank"
             rel="noopener" id="link-liberacao">Avisar no WhatsApp para liberar</a></p>`
      : ""}
    ${perfil.admin ? '<p><a class="btn-primario" href="admin.html">Abrir painel</a></p>' : ""}`;

  const lista = $("#lista-pedidos");
  lista.innerHTML = '<p class="vazio">Carregando…</p>';
  try {
    const pedidos = await sistema.meusPedidos();
    lista.innerHTML = pedidos.length
      ? pedidos.map(cartaoPedido).join("")
      : '<p class="vazio">Você ainda não fez pedidos.<br>'
        + '<a href="index.html">Ir para o catálogo</a></p>';
  } catch (erro) {
    lista.innerHTML = `<p class="erro">${escapar(erro.message)}</p>`;
  }
}

function cartaoPedido(pedido) {
  const st = sistema.STATUS[pedido.status] || { rotulo: pedido.status, cor: "#64748b" };
  const itens = pedido.pedido_itens || [];
  const eventos = [...(pedido.pedido_eventos || [])]
    .sort((a, b) => new Date(a.criado_em) - new Date(b.criado_em));
  return `
  <article class="cartao pedido">
    <header class="pedido-topo">
      <div>
        <b>Pedido ${escapar(pedido.numero)}</b>
        <div class="cod">${dataBR(pedido.criado_em)}</div>
      </div>
      <span class="etiqueta" style="background:${st.cor}">${escapar(st.rotulo)}</span>
    </header>
    <table class="tabela">
      <tbody>
        ${itens.map((i) => `<tr>
          <td>${escapar(i.nome)}<div class="cod">${escapar(i.codigo)}</div></td>
          <td class="num">${i.caixas} cx<div class="cod">${i.pecas} pç</div></td>
          <td class="num">${formatarBRL(Number(i.preco_unit))}</td>
          <td class="num"><b>${formatarBRL(Number(i.subtotal))}</b></td>
        </tr>`).join("")}
      </tbody>
      <tfoot><tr><td colspan="3">Total</td>
        <td class="num"><b>${formatarBRL(Number(pedido.total))}</b></td></tr></tfoot>
    </table>
    ${pedido.observacao ? `<p class="ajuda">Obs.: ${escapar(pedido.observacao)}</p>` : ""}
    <ol class="linha-tempo">
      ${eventos.map((e) => {
        const s = sistema.STATUS[e.status] || { rotulo: e.status, cor: "#64748b" };
        return `<li><span class="ponto" style="background:${s.cor}"></span>
                ${escapar(s.rotulo)} <small>${dataBR(e.criado_em)}</small></li>`;
      }).join("")}
    </ol>
  </article>`;
}

function ligarEventos() {
  const trocarAba = (entrar) => {
    $("#aba-entrar").setAttribute("aria-current", String(entrar));
    $("#aba-cadastrar").setAttribute("aria-current", String(!entrar));
    $("#form-entrar").hidden = !entrar;
    $("#form-cadastrar").hidden = entrar;
  };
  $("#aba-entrar").addEventListener("click", () => trocarAba(true));
  $("#aba-cadastrar").addEventListener("click", () => trocarAba(false));

  $("#form-entrar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const erro = form.querySelector(".erro");
    erro.hidden = true;
    form.querySelector("button").disabled = true;
    try {
      const perfil = await sistema.entrar(form.email.value.trim(), form.senha.value);
      voltarOuMostrar(perfil);
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
    } finally {
      form.querySelector("button").disabled = false;
    }
  });

  $("#form-cadastrar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const erro = form.querySelector(".erro");
    erro.hidden = true;
    form.querySelector("button").disabled = true;
    try {
      const perfil = await sistema.cadastrar({
        email: form.email.value.trim(),
        senha: form.senha.value,
        razao_social: form.razao_social.value.trim(),
        cnpj: form.cnpj.value.trim(),
        telefone: form.telefone.value.trim(),
        cidade: form.cidade.value.trim() || null,
        uf: form.uf.value.trim().toUpperCase() || null,
      });
      voltarOuMostrar(perfil);
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
    } finally {
      form.querySelector("button").disabled = false;
    }
  });

  $("#btn-sair").addEventListener("click", async () => {
    await sistema.sair();
    location.href = "index.html";
  });
}

/** Link para o cliente avisar que se cadastrou e pedir a liberação. */
function linkLiberacao(perfil) {
  const numero = (CFG.whatsapp || "").replace(/\D/g, "");
  if (!numero || /^5*0+$/.test(numero)) return null;
  const texto = `Olá! Fiz meu cadastro no site.\n`
    + `Empresa: ${perfil.razao_social}\nCNPJ: ${perfil.cnpj}\n`
    + `Pode liberar meu acesso aos preços?`;
  return `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`;
}

function voltarOuMostrar(perfil) {
  if (sessionStorage.getItem("voltar-para") === "pedido" && perfil?.aprovado) {
    location.href = "index.html";
    return;
  }
  mostrarPedidos(perfil);
}

iniciar();
