"""Serviço de Processamento: consome o Serviço de Dados por HTTP e calcula as análises de estoque.

Este serviço NÃO acessa o banco SQLite: tudo que ele sabe vem das respostas HTTP do Serviço de Dados.
"""
import os

import requests
from flask import Flask, jsonify

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False  # mantém a ordem dos campos como escrita no código

# Endereço do Serviço de Dados. Sem Docker: localhost. No Docker Compose será
# definido por variável de ambiente como http://servico-dados:5001
DADOS_URL = os.environ.get("DADOS_URL", "http://localhost:5001").rstrip("/")
TIMEOUT = 5  # segundos de espera por resposta do Serviço de Dados


class ErroServicoDados(Exception):
    """Falha ao obter dados do Serviço de Dados."""

    def __init__(self, mensagem, status):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def buscar(caminho):
    """GET no Serviço de Dados; converte falhas de rede em ErroServicoDados."""
    url = f"{DADOS_URL}{caminho}"
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise ErroServicoDados("Serviço de Dados não respondeu a tempo.", 504)
    except requests.exceptions.ConnectionError:
        raise ErroServicoDados("Serviço de Dados indisponível.", 503)
    if resp.status_code != 200:
        raise ErroServicoDados(
            f"Serviço de Dados retornou HTTP {resp.status_code} em {caminho}.", 502
        )
    return resp.json()


@app.errorhandler(ErroServicoDados)
def tratar_erro_dados(e):
    return jsonify({"erro": e.mensagem}), e.status


@app.get("/health")
def health():
    return jsonify({"status": "ok", "servico": "servico-processamento"})


@app.get("/analises/estoque")
def analise_estoque():
    produtos = buscar("/produtos")
    movimentacoes = buscar("/movimentacoes")

    # Agrupa as movimentações por produto (uma passada só)
    acumulado = {}
    for m in movimentacoes:
        a = acumulado.setdefault(
            m["produto_id"],
            {"entradas": 0, "saidas": 0, "qtd_mov": 0, "ultima": None},
        )
        if m["tipo"] == "entrada":
            a["entradas"] += m["quantidade"]
        else:
            a["saidas"] += m["quantidade"]
        a["qtd_mov"] += 1
        if a["ultima"] is None or m["data"] > a["ultima"]:
            a["ultima"] = m["data"]

    itens = []
    for p in produtos:
        a = acumulado.get(
            p["id"], {"entradas": 0, "saidas": 0, "qtd_mov": 0, "ultima": None}
        )
        saldo = a["entradas"] - a["saidas"]
        itens.append(
            {
                "produto_id": p["id"],
                "nome": p["nome"],
                "preco": p["preco"],
                "estoque_minimo": p["estoque_minimo"],
                "total_entradas": a["entradas"],
                "total_saidas": a["saidas"],
                "saldo": saldo,
                # Regra: abaixo do mínimo = saldo ESTRITAMENTE menor que o mínimo
                "abaixo_minimo": saldo < p["estoque_minimo"],
                "valor_em_estoque": round(saldo * p["preco"], 2),
                "total_movimentacoes": a["qtd_mov"],
                "ultima_movimentacao": a["ultima"],
            }
        )

    mais_saidas = max(itens, key=lambda i: i["total_saidas"], default=None)
    resumo = {
        "total_produtos": len(itens),
        "produtos_abaixo_minimo": sum(1 for i in itens if i["abaixo_minimo"]),
        "total_entradas": sum(i["total_entradas"] for i in itens),
        "total_saidas": sum(i["total_saidas"] for i in itens),
        "total_movimentacoes": sum(i["total_movimentacoes"] for i in itens),
        "valor_total_em_estoque": round(sum(i["valor_em_estoque"] for i in itens), 2),
        "produto_mais_saidas": (
            mais_saidas["nome"] if mais_saidas and mais_saidas["total_saidas"] > 0 else None
        ),
    }
    return jsonify({"resumo": resumo, "produtos": itens})


@app.errorhandler(404)
def nao_encontrado(_):
    return jsonify({"erro": "Rota não encontrada."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)