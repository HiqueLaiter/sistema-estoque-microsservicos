"""Serviço de Dados: persiste produtos e movimentações (SQLite) e 
    expõe uma API HTTP/JSON."""
from datetime import datetime

from flask import Flask, jsonify, request

from database import get_connection, init_db

app = Flask(__name__)
app.json.ensure_ascii = False  # mantém acentos legíveis no JSON
init_db()


def erro(mensagem, status):
    return jsonify({"erro": mensagem}), status


def eh_inteiro(valor):
    # bool é subclasse de int em Python; não aceita true/false como número
    return isinstance(valor, int) and not isinstance(valor, bool)


def eh_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "servico": "servico-dados"})


# ---------- Produtos ----------
@app.post("/produtos")
def criar_produto():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return erro("Corpo da requisição deve ser um JSON válido.", 400)

    nome = dados.get("nome")
    preco = dados.get("preco")
    estoque_minimo = dados.get("estoque_minimo", 0)

    if not isinstance(nome, str) or not nome.strip():
        return erro("'nome' é obrigatório e deve ser texto não vazio.", 400)
    if not eh_numero(preco) or preco < 0:
        return erro("'preco' é obrigatório e deve ser um número >= 0.", 400)
    if not eh_inteiro(estoque_minimo) or estoque_minimo < 0:
        return erro("'estoque_minimo' deve ser um inteiro >= 0.", 400)

    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO produtos (nome, preco, estoque_minimo) VALUES (?, ?, ?)",
            (nome.strip(), preco, estoque_minimo),
        )
        produto = conn.execute(
            "SELECT * FROM produtos WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return jsonify(dict(produto)), 201
    finally:
        conn.close()


@app.get("/produtos")
def listar_produtos():
    conn = get_connection()
    try:
        linhas = conn.execute("SELECT * FROM produtos ORDER BY id").fetchall()
        return jsonify([dict(l) for l in linhas])
    finally:
        conn.close()


@app.get("/produtos/<int:produto_id>")
def obter_produto(produto_id):
    conn = get_connection()
    try:
        produto = conn.execute(
            "SELECT * FROM produtos WHERE id = ?", (produto_id,)
        ).fetchone()
        if produto is None:
            return erro("Produto não encontrado.", 404)
        return jsonify(dict(produto))
    finally:
        conn.close()


# ---------- Movimentações ----------
@app.post("/movimentacoes")
def registrar_movimentacao():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return erro("Corpo da requisição deve ser um JSON válido.", 400)

    produto_id = dados.get("produto_id")
    tipo = dados.get("tipo")
    quantidade = dados.get("quantidade")

    if not eh_inteiro(produto_id):
        return erro("'produto_id' é obrigatório e deve ser um inteiro.", 400)
    if tipo not in ("entrada", "saida"):
        return erro("'tipo' deve ser 'entrada' ou 'saida'.", 400)
    if not eh_inteiro(quantidade) or quantidade <= 0:
        return erro("'quantidade' deve ser um inteiro maior que zero.", 400)

    conn = get_connection()
    try:
        # BEGIN IMMEDIATE trava a escrita: a checagem do saldo e o INSERT ocorrem
        # na mesma transação, então duas saídas simultâneas não "furam" a validação.
        conn.execute("BEGIN IMMEDIATE")
        try:
            produto = conn.execute(
                "SELECT id FROM produtos WHERE id = ?", (produto_id,)
            ).fetchone()
            if produto is None:
                conn.execute("ROLLBACK")
                return erro("Produto não encontrado.", 404)

            if tipo == "saida":
                saldo = conn.execute(
                    """SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada'
                                                THEN quantidade ELSE -quantidade END), 0)
                       FROM movimentacoes WHERE produto_id = ?""",
                    (produto_id,),
                ).fetchone()[0]
                if quantidade > saldo:
                    conn.execute("ROLLBACK")
                    return (
                        jsonify(
                            {
                                "erro": "Saldo insuficiente: a saída deixaria o estoque negativo.",
                                "saldo_atual": saldo,
                                "quantidade_solicitada": quantidade,
                            }
                        ),
                        409,
                    )

            data = datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                "INSERT INTO movimentacoes (produto_id, tipo, quantidade, data) "
                "VALUES (?, ?, ?, ?)",
                (produto_id, tipo, quantidade, data),
            )
            mov = conn.execute(
                "SELECT * FROM movimentacoes WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            conn.execute("COMMIT")
            return jsonify(dict(mov)), 201
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


@app.get("/movimentacoes")
def listar_movimentacoes():
    """Lista o histórico. Filtro opcional: /movimentacoes?produto_id=1"""
    produto_id = request.args.get("produto_id")
    conn = get_connection()
    try:
        if produto_id is not None:
            if not produto_id.isdigit():
                return erro("'produto_id' deve ser um inteiro.", 400)
            linhas = conn.execute(
                "SELECT * FROM movimentacoes WHERE produto_id = ? ORDER BY id",
                (int(produto_id),),
            ).fetchall()
        else:
            linhas = conn.execute("SELECT * FROM movimentacoes ORDER BY id").fetchall()
        return jsonify([dict(l) for l in linhas])
    finally:
        conn.close()


@app.errorhandler(404)
def nao_encontrado(_):
    return erro("Rota não encontrada.", 404)


@app.errorhandler(405)
def metodo_nao_permitido(_):
    return erro("Método não permitido para esta rota.", 405)


if __name__ == "__main__":
    # host 0.0.0.0 é necessário para o contêiner aceitar conexões de fora dele
    app.run(host="0.0.0.0", port=5001)