"""Serviço de Relatórios: orquestra o Serviço de Dados e o Serviço de Processamento
e consolida o resultado em um relatório final (JSON ou CSV).

Este serviço NÃO acessa o banco e NÃO recalcula saldos: ele só chama os outros dois
serviços por HTTP e organiza as respostas.
"""
import csv
import io
import os
from datetime import datetime

import requests
from flask import Flask, Response, jsonify

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False

# Endereços dos outros serviços. Sem Docker: localhost. No Docker Compose serão
# definidos por variável de ambiente (http://servico-dados:5001 etc.).
DADOS_URL = os.environ.get("DADOS_URL", "http://localhost:5001").rstrip("/")
PROCESSAMENTO_URL = os.environ.get("PROCESSAMENTO_URL", "http://localhost:5002").rstrip("/")
TIMEOUT = 10  # o processamento ainda chama o Serviço de Dados, então damos mais tempo
QTD_ULTIMAS_MOVIMENTACOES = 10


class ErroServico(Exception):
    def __init__(self, mensagem, status):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def chamar(nome, base, caminho):
    """GET em outro serviço; converte falhas em ErroServico com status HTTP adequado."""
    try:
        resp = requests.get(f"{base}{caminho}", timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise ErroServico(f"{nome} não respondeu a tempo.", 504)
    except requests.exceptions.ConnectionError:
        raise ErroServico(f"{nome} indisponível.", 503)
    if resp.status_code != 200:
        detalhe = ""
        try:
            detalhe = f" ({resp.json().get('erro', '')})"
        except ValueError:
            pass
        raise ErroServico(f"{nome} falhou com HTTP {resp.status_code}{detalhe}.", 502)
    return resp.json()


@app.errorhandler(ErroServico)
def tratar_erro(e):
    return jsonify({"erro": e.mensagem}), e.status


def montar_relatorio():
    """Orquestração: 1) pede a análise ao Processamento; 2) pede o histórico ao Dados."""
    analise = chamar("Serviço de Processamento", PROCESSAMENTO_URL, "/analises/estoque")
    movimentacoes = chamar("Serviço de Dados", DADOS_URL, "/movimentacoes")

    produtos = analise["produtos"]
    nomes = {p["produto_id"]: p["nome"] for p in produtos}

    alertas = [
        {
            "produto_id": p["produto_id"],
            "nome": p["nome"],
            "saldo": p["saldo"],
            "estoque_minimo": p["estoque_minimo"],
            "falta_para_o_minimo": p["estoque_minimo"] - p["saldo"],
        }
        for p in produtos
        if p["abaixo_minimo"]
    ]

    recentes = sorted(movimentacoes, key=lambda m: m["id"], reverse=True)
    recentes = recentes[:QTD_ULTIMAS_MOVIMENTACOES]
    ultimas = [
        {
            "id": m["id"],
            "data": m["data"],
            "produto_id": m["produto_id"],
            "produto": nomes.get(m["produto_id"], "(desconhecido)"),
            "tipo": m["tipo"],
            "quantidade": m["quantidade"],
        }
        for m in recentes
    ]

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "fontes": ["servico-dados", "servico-processamento"],
        "resumo": analise["resumo"],
        "alertas": alertas,
        "produtos": produtos,
        "ultimas_movimentacoes": ultimas,
    }


def num_br(valor):
    """Formata número com vírgula decimal, para abrir corretamente no Excel em pt-BR."""
    return f"{valor:.2f}".replace(".", ",")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "servico": "servico-relatorios"})


@app.get("/relatorios/estoque")
def relatorio_json():
    return jsonify(montar_relatorio())


@app.get("/relatorios/estoque.csv")
def relatorio_csv():
    relatorio = montar_relatorio()

    saida = io.StringIO()
    # ';' como separador porque o Excel em pt-BR usa vírgula como decimal
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        [
            "produto_id", "nome", "preco", "estoque_minimo", "total_entradas",
            "total_saidas", "saldo", "abaixo_minimo", "valor_em_estoque",
        ]
    )
    for p in relatorio["produtos"]:
        escritor.writerow(
            [
                p["produto_id"], p["nome"], num_br(p["preco"]), p["estoque_minimo"],
                p["total_entradas"], p["total_saidas"], p["saldo"],
                "sim" if p["abaixo_minimo"] else "nao", num_br(p["valor_em_estoque"]),
            ]
        )

    # utf-8-sig acrescenta o BOM, que faz o Excel reconhecer os acentos
    corpo = saida.getvalue().encode("utf-8-sig")
    return Response(
        corpo,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=relatorio_estoque.csv"},
    )


@app.errorhandler(404)
def nao_encontrado(_):
    return jsonify({"erro": "Rota não encontrada."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)