/* Regras de preço e de quantidade do catálogo Knup.
   Ficam separadas porque valem igual no catálogo, no pedido e no painel. */

/** "1.148,85" -> 1148.85 */
function paraNumero(preco) {
  return Number(String(preco ?? "").replace(/\./g, "").replace(",", ".")) || 0;
}

function formatarBRL(n) {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Peças de um item: a venda é em caixa fechada, salvo produto sem caixa definida. */
function pecasDe(produto, caixas) {
  return (produto.qtd_caixa || 1) * caixas;
}

/**
 * Preço unitário aplicável ao volume pedido.
 * O catálogo traz faixas como "3 CX" (a partir de 3 caixas) e "50 PÇS"
 * (a partir de 50 peças); vale sempre a faixa mais vantajosa que o volume atinge.
 */
function precoUnitario(info, produto, caixas) {
  if (!info) return 0;
  let valor = paraNumero(info.valor);
  const pecas = pecasDe(produto, caixas);
  for (const faixa of info.faixas || []) {
    const atingiu = faixa.unidade === "pc" ? pecas >= faixa.a_partir : caixas >= faixa.a_partir;
    if (atingiu) valor = Math.min(valor, paraNumero(faixa.valor));
  }
  return valor;
}

/** Texto curto das faixas, para mostrar no card e na ficha. */
function textoDasFaixas(info) {
  return (info?.faixas || [])
    .map((f) => `${f.a_partir} ${f.unidade === "pc" ? "pç" : "cx"}: ${formatarBRL(paraNumero(f.valor))}`)
    .join(" · ");
}

function temPromocao(info) {
  return Boolean(info?.de);
}

/** Desconto da promoção em %, para o selo. */
function descontoPercentual(info) {
  if (!temPromocao(info)) return 0;
  const de = paraNumero(info.de);
  const por = paraNumero(info.valor);
  return de > por ? Math.round((1 - por / de) * 100) : 0;
}

if (typeof module !== "undefined") {
  module.exports = { paraNumero, formatarBRL, pecasDe, precoUnitario,
                     textoDasFaixas, temPromocao, descontoPercentual };
}
