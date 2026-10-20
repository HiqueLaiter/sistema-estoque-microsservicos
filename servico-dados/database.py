"""Acesso ao banco SQLite. Somente o Serviço de Dados usa este módulo."""
import os
import sqlite3

# Caminho do banco: vem da variável de ambiente DB_PATH.
# Padrão (rodando sem Docker): sistema-estoque/dados/estoque.db
_PADRAO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "dados", "estoque.db"
)
DB_PATH = os.path.abspath(os.environ.get("DB_PATH", _PADRAO))


def get_connection():
    """Abre uma conexão nova. isolation_level=None = autocommit;
    as transações são controladas manualmente (BEGIN IMMEDIATE / COMMIT)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # No SQLite as chaves estrangeiras vêm desligadas: precisa ativar a cada conexão.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Cria as tabelas, se ainda não existirem."""
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS produtos (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                nome           TEXT    NOT NULL,
                preco          REAL    NOT NULL CHECK (preco >= 0),
                estoque_minimo INTEGER NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0)
            );

            CREATE TABLE IF NOT EXISTS movimentacoes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id INTEGER NOT NULL REFERENCES produtos(id),
                tipo       TEXT    NOT NULL CHECK (tipo IN ('entrada', 'saida')),
                quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                data       TEXT    NOT NULL
            );
            """
        )
    finally:
        conn.close()