// Frontend mínimo. Fala só com o nginx (mesma origem), que repassa para os serviços:
//   /api/dados/...   -> Serviço de Dados      (cadastro e movimentações)
//   /relatorios/...  -> Serviço de Relatórios (relatório JSON/CSV)
const API_DADOS = "/api/dados";
const URL_RELATORIO = "/relatorios/estoque";

const $ = (id) => document.getElementById(id);
const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

// Cria um elemento com texto. Usa textContent (nunca innerHTML) para que nomes
// de produtos digitados pelo usuário não sejam interpretados como HTML.
function el(tag, texto, classe) {
  const e = document.createElement(tag);
  if (texto !== undefined && texto !== null) e.textContent = texto;
  if (classe) e.className = classe;
  return e;
}

function mostrarMensagem(texto, tipo) {
  const caixa = $("mensagem");
  caixa.textContent = texto;
  caixa.className = "mensagem " + tipo;
}

// Faz a requisição e converte erros (rede ou HTTP) em Error com mensagem legível.
async function chamar(url, opcoes) {
  let resp;
  try {
    resp = await fetch(url, opcoes);
  } catch (e) {
    throw new Error("Não foi possível conectar ao servidor.");
  }
  let corpo = null;
  try {
    corpo = await resp.json();
  } catch (e) {
    // resposta sem JSON: segue com corpo nulo
  }
  if (!resp.ok) {
    let msg = (corpo && corpo.erro) || "Erro HTTP " + resp.status;
    if (corpo && corpo.saldo_atual !== undefined) {
      msg += " (saldo atual: " + corpo.saldo_atual + ")";
    }
    throw new Error(msg);
  }
  return corpo;
}

function enviarJson(corpo) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  };
}

// ---------- Produtos (lista do select) ----------
async function carregarProdutos() {
  const produtos = await chamar(API_DADOS + "/produtos");
  const select = $("mov-produto");
  const selecionado = select.value;
  select.replaceChildren();
  if (produtos.length === 0) {
    const op = el("option", "Cadastre um produto primeiro");
    op.value = "";
    select.appendChild(op);
    return;
  }
  for (const p of produtos) {
    const op = el("option", p.nome);
    op.value = String(p.id);
    select.appendChild(op);
  }
  if (selecionado) select.value = selecionado;
}

// ---------- Relatório ----------
function cartao(rotulo, valor) {
  const c = el("div", null, "cartao");
  c.appendChild(el("div", rotulo, "rotulo"));
  c.appendChild(el("div", valor, "valor"));
  return c;
}

function celula(texto, numerica) {
  return el("td", texto, numerica ? "num" : "");
}

function renderizarRelatorio(r) {
  $("gerado-em").textContent = "Gerado em " + r.gerado_em.replace("T", " ");

  const resumo = $("resumo");
  resumo.replaceChildren(
    cartao("Produtos", r.resumo.total_produtos),
    cartao("Abaixo do mínimo", r.resumo.produtos_abaixo_minimo),
    cartao("Total de entradas", r.resumo.total_entradas),
    cartao("Total de saídas", r.resumo.total_saidas),
    cartao("Valor em estoque", moeda.format(r.resumo.valor_total_em_estoque))
  );

  const alertas = $("alertas");
  alertas.replaceChildren();
  if (r.alertas.length === 0) {
    alertas.appendChild(el("div", "Nenhum produto abaixo do estoque mínimo.", "caixa-ok"));
  } else {
    const caixa = el("div", null, "caixa-alerta");
    caixa.appendChild(el("strong", "Atenção: estoque abaixo do mínimo"));
    const lista = el("ul");
    for (const a of r.alertas) {
      lista.appendChild(
        el("li", a.nome + ": saldo " + a.saldo + ", mínimo " + a.estoque_minimo +
          " (faltam " + a.falta_para_o_minimo + ")")
      );
    }
    caixa.appendChild(lista);
    alertas.appendChild(caixa);
  }

  const corpoProdutos = document.querySelector("#tabela-produtos tbody");
  corpoProdutos.replaceChildren();
  if (r.produtos.length === 0) {
    const tr = el("tr");
    const td = el("td", "Nenhum produto cadastrado.");
    td.colSpan = 8;
    tr.appendChild(td);
    corpoProdutos.appendChild(tr);
  }
  for (const p of r.produtos) {
    const tr = el("tr");
    tr.appendChild(celula(p.nome));
    tr.appendChild(celula(moeda.format(p.preco), true));
    tr.appendChild(celula(p.total_entradas, true));
    tr.appendChild(celula(p.total_saidas, true));
    tr.appendChild(celula(p.saldo, true));
    tr.appendChild(celula(p.estoque_minimo, true));
    const situacao = el("td");
    situacao.appendChild(
      p.abaixo_minimo
        ? el("span", "Abaixo do mínimo", "selo baixo")
        : el("span", "OK", "selo ok")
    );
    tr.appendChild(situacao);
    tr.appendChild(celula(moeda.format(p.valor_em_estoque), true));
    corpoProdutos.appendChild(tr);
  }

  const corpoMov = document.querySelector("#tabela-movimentacoes tbody");
  corpoMov.replaceChildren();
  if (r.ultimas_movimentacoes.length === 0) {
    const tr = el("tr");
    const td = el("td", "Nenhuma movimentação registrada.");
    td.colSpan = 4;
    tr.appendChild(td);
    corpoMov.appendChild(tr);
  }
  for (const m of r.ultimas_movimentacoes) {
    const tr = el("tr");
    tr.appendChild(celula(m.data.replace("T", " ")));
    tr.appendChild(celula(m.produto));
    tr.appendChild(celula(m.tipo === "entrada" ? "Entrada" : "Saída"));
    tr.appendChild(celula(m.quantidade, true));
    corpoMov.appendChild(tr);
  }
}

async function carregarRelatorio() {
  const relatorio = await chamar(URL_RELATORIO);
  renderizarRelatorio(relatorio);
}

// Atualiza select e relatório; erros viram mensagem na tela.
async function atualizarTudo() {
  try {
    await carregarProdutos();
    await carregarRelatorio();
  } catch (e) {
    mostrarMensagem("Falha ao atualizar: " + e.message, "erro");
  }
}

// ---------- Formulários ----------
$("form-produto").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const corpo = {
    nome: $("produto-nome").value.trim(),
    preco: Number($("produto-preco").value),
    estoque_minimo: parseInt($("produto-minimo").value || "0", 10),
  };
  try {
    const criado = await chamar(API_DADOS + "/produtos", enviarJson(corpo));
    mostrarMensagem('Produto "' + criado.nome + '" cadastrado (id ' + criado.id + ").", "sucesso");
    $("form-produto").reset();
    await atualizarTudo();
  } catch (e) {
    mostrarMensagem("Erro ao cadastrar: " + e.message, "erro");
  }
});

$("form-movimentacao").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const corpo = {
    produto_id: parseInt($("mov-produto").value, 10),
    tipo: $("mov-tipo").value,
    quantidade: parseInt($("mov-quantidade").value, 10),
  };
  try {
    const mov = await chamar(API_DADOS + "/movimentacoes", enviarJson(corpo));
    mostrarMensagem(
      (mov.tipo === "entrada" ? "Entrada" : "Saída") + " de " + mov.quantidade + " registrada.",
      "sucesso"
    );
    $("mov-quantidade").value = "";
    await atualizarTudo();
  } catch (e) {
    mostrarMensagem("Movimentação rejeitada: " + e.message, "erro");
  }
});

$("btn-atualizar").addEventListener("click", atualizarTudo);

atualizarTudo();