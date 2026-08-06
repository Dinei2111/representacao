/* Camada de acesso ao Supabase: sessão, perfil, preços e pedidos.
   Compartilhada pelo catálogo, pela conta do cliente e pelo painel.

   Sem chaves preenchidas em config.js, `sistema.ativo` é false e o site
   funciona como catálogo + WhatsApp, sem nenhuma chamada de rede. */

const sistema = (() => {
  const cfg = window.CONFIG || {};
  const ativo = Boolean(cfg.supabaseUrl && cfg.supabaseAnonKey && window.supabase);
  const db = ativo
    ? window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey)
    : null;

  const STATUS = {
    pendente:  { rotulo: "Pendente",  cor: "#b45309", ordem: 1 },
    pago:      { rotulo: "Pago",      cor: "#0369a1", ordem: 2 },
    faturado:  { rotulo: "Faturado",  cor: "#7c3aed", ordem: 3 },
    enviado:   { rotulo: "Enviado",   cor: "#0891b2", ordem: 4 },
    entregue:  { rotulo: "Entregue",  cor: "#15803d", ordem: 5 },
    cancelado: { rotulo: "Cancelado", cor: "#b91c1c", ordem: 6 },
  };

  let perfilAtual = null;

  async function usuario() {
    if (!ativo) return null;
    const { data } = await db.auth.getUser();
    return data?.user || null;
  }

  /** Perfil do cliente logado (com `aprovado` e `admin`); null se não houver sessão. */
  async function perfil(recarregar = false) {
    if (!ativo) return null;
    if (perfilAtual && !recarregar) return perfilAtual;
    const u = await usuario();
    if (!u) return (perfilAtual = null);
    const { data } = await db.from("perfis").select("*").eq("id", u.id).maybeSingle();
    perfilAtual = data ? { ...data, email: u.email } : null;
    return perfilAtual;
  }

  async function entrar(email, senha) {
    const { error } = await db.auth.signInWithPassword({ email, password: senha });
    if (error) throw new Error(traduzirErro(error.message));
    perfilAtual = null;
    return perfil(true);
  }

  async function cadastrar(dados) {
    const { email, senha, ...resto } = dados;
    const { data, error } = await db.auth.signUp({ email, password: senha });
    if (error) throw new Error(traduzirErro(error.message));
    // sem confirmação de e-mail a sessão já vem pronta; com ela, o cliente
    // precisa confirmar antes de o perfil poder ser gravado
    if (!data.session) {
      throw new Error("Confira seu e-mail para confirmar o cadastro e depois faça login.");
    }
    const { error: erroPerfil } = await db.from("perfis").insert({ id: data.user.id, ...resto });
    if (erroPerfil) throw new Error(traduzirErro(erroPerfil.message));
    perfilAtual = null;
    return perfil(true);
  }

  async function sair() {
    if (ativo) await db.auth.signOut();
    perfilAtual = null;
  }

  /** Tabela de preços — o banco só devolve algo para cliente aprovado. */
  async function precos() {
    if (!ativo) return null;
    const { data, error } = await db.from("precos").select("codigo, de, valor, faixas");
    if (error || !data?.length) return null;
    return Object.fromEntries(data.map((p) => [p.codigo, p]));
  }

  /** Grava o pedido e devolve o registro criado (com número). */
  async function criarPedido(itens, observacao) {
    const total = itens.reduce((s, i) => s + i.subtotal, 0);
    const { data: pedido, error } = await db
      .from("pedidos")
      .insert({ total, observacao })
      .select()
      .single();
    if (error) throw new Error(traduzirErro(error.message));

    const linhas = itens.map((i) => ({ pedido_id: pedido.id, ...i }));
    const { error: erroItens } = await db.from("pedido_itens").insert(linhas);
    if (erroItens) throw new Error(traduzirErro(erroItens.message));
    return pedido;
  }

  async function meusPedidos() {
    const { data, error } = await db
      .from("pedidos")
      .select("*, pedido_itens(*), pedido_eventos(*)")
      .order("criado_em", { ascending: false });
    if (error) throw new Error(traduzirErro(error.message));
    return data || [];
  }

  // --- somente admin ---------------------------------------------------------
  async function todosPedidos(status) {
    let q = db.from("pedidos").select("*, pedido_itens(*), perfis(*)")
      .order("criado_em", { ascending: false });
    if (status) q = q.eq("status", status);
    const { data, error } = await q;
    if (error) throw new Error(traduzirErro(error.message));
    return data || [];
  }

  async function mudarStatus(pedidoId, status) {
    const { error } = await db.from("pedidos").update({ status }).eq("id", pedidoId);
    if (error) throw new Error(traduzirErro(error.message));
  }

  async function clientes(apenasPendentes = false) {
    let q = db.from("perfis").select("*").order("criado_em", { ascending: false });
    if (apenasPendentes) q = q.eq("aprovado", false);
    const { data, error } = await q;
    if (error) throw new Error(traduzirErro(error.message));
    return data || [];
  }

  async function aprovarCliente(id, aprovado = true) {
    const { error } = await db.from("perfis").update({ aprovado }).eq("id", id);
    if (error) throw new Error(traduzirErro(error.message));
  }

  function traduzirErro(msg = "") {
    const m = msg.toLowerCase();
    if (m.includes("invalid login")) return "E-mail ou senha incorretos.";
    if (m.includes("already registered")) return "Este e-mail já tem cadastro. Faça login.";
    if (m.includes("password")) return "A senha precisa ter pelo menos 6 caracteres.";
    if (m.includes("duplicate key") && m.includes("cnpj")) return "Este CNPJ já está cadastrado.";
    if (m.includes("row-level security") || m.includes("permission"))
      return "Seu cadastro ainda não foi aprovado.";
    return msg || "Não foi possível concluir. Tente de novo.";
  }

  return { ativo, db, STATUS, usuario, perfil, entrar, cadastrar, sair, precos,
           criarPedido, meusPedidos, todosPedidos, mudarStatus, clientes,
           aprovarCliente };
})();

if (typeof module !== "undefined") module.exports = { sistema };
