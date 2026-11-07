"""Persistent store scoped by server-side STORE_ID; never accepts a tenant from forms."""
import json
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime

from config import get_setting, load_settings
from database import DatabaseConfigError, get_sqlite_connection

STATUSES = {
    'novo': 'Novo', 'em_atendimento': 'Em atendimento',
    'orcamento_enviado': 'Orçamento enviado', 'venda_concluida': 'Venda concluída',
    'perdido': 'Perdido',
}

class Repository:
    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.tenant = get_setting('STORE_ID', 'kika-cakes')
        if self.settings.db_backend != 'sqlite':
            raise DatabaseConfigError('Painel persistente requer DB_BACKEND=sqlite. Não há fallback para outro banco.')
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS leads (
                    tenant TEXT NOT NULL, protocol TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'novo',
                    PRIMARY KEY (tenant, protocol), UNIQUE (tenant, fingerprint));
                CREATE TABLE IF NOT EXISTS products (
                    tenant TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (tenant, id));
            ''')

    def products(self):
        from services.catalog import Product, _SAMPLE_PRODUCTS
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            # Seed only once per tenant; edits are never overwritten on restart.
            for product in _SAMPLE_PRODUCTS:
                conn.execute('INSERT OR IGNORE INTO products VALUES (?, ?, ?)',
                             (self.tenant, product.id, json.dumps(asdict(product))))
            rows = conn.execute('SELECT payload FROM products WHERE tenant=? ORDER BY id', (self.tenant,)).fetchall()
        return [Product(**json.loads(row['payload'])) for row in rows]

    def save_product(self, product):
        import math
        from services.catalog import PRICE_FROM, PRICE_ESTIMATED, PRICE_ON_REQUEST
        if not all(str(v).strip() for v in (product.id, product.name, product.category, product.unit)):
            raise ValueError('Informe identificador, nome, categoria e unidade.')
        if product.price_type not in (PRICE_FROM, PRICE_ESTIMATED, PRICE_ON_REQUEST):
            raise ValueError('Tipo de preço inválido.')
        if product.price_type != PRICE_ON_REQUEST and (product.price is None or not math.isfinite(product.price) or product.price < 0):
            raise ValueError('Preço deve ser um número não negativo.')
        if not (1 <= product.min_qty <= product.max_qty <= 1000):
            raise ValueError('Quantidades devem estar entre 1 e 1000, com mínimo menor ou igual ao máximo.')
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            conn.execute('INSERT INTO products VALUES (?, ?, ?) ON CONFLICT(tenant,id) DO UPDATE SET payload=excluded.payload',
                         (self.tenant, product.id, json.dumps(asdict(product))))

    def add(self, quote):
        from services.quotes import DuplicateQuoteError
        import sqlite3
        # A public request can only enter as a new lead.
        quote.status = 'novo'
        try:
            with closing(get_sqlite_connection(self.settings)) as conn, conn:
                conn.execute('INSERT INTO leads VALUES (?, ?, ?, ?, ?)',
                             (self.tenant, quote.protocol, quote.fingerprint, json.dumps(quote.to_record()), 'novo'))
        except sqlite3.IntegrityError:
            existing = next((q for q in self.all() if q.fingerprint == quote.fingerprint), None)
            if existing is not None:
                raise DuplicateQuoteError(existing)
            raise
        return quote

    def all(self, status=None, start=None, end=None):
        from services.quotes import QuoteRequest
        if start and end and start > end:
            raise ValueError('Data inicial deve ser anterior ou igual à final.')
        with closing(get_sqlite_connection(self.settings)) as conn:
            rows = conn.execute('SELECT payload, status FROM leads WHERE tenant=? ORDER BY rowid DESC', (self.tenant,)).fetchall()
        result = []
        for row in rows:
            data = json.loads(row['payload'])
            data.pop('fingerprint', None)
            data['desired_date'] = date.fromisoformat(data['desired_date'])
            data['created_at'] = datetime.fromisoformat(data['created_at'])
            data['status'] = row['status']
            quote = QuoteRequest(**data)
            day = quote.created_at.date()
            if (not status or quote.status == status) and (not start or day >= start) and (not end or day <= end):
                result.append(quote)
        return result

    def update_status(self, protocol, status, confirm_sale=False):
        if status not in STATUSES:
            raise ValueError('Status inválido.')
        if status == 'venda_concluida' and not confirm_sale:
            raise ValueError('Confirme manualmente a venda concluída.')
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            cursor = conn.execute('UPDATE leads SET status=? WHERE tenant=? AND protocol=?', (status, self.tenant, protocol))
            if cursor.rowcount != 1:
                raise ValueError('Solicitação não encontrada nesta confeitaria.')


def indicators(leads):
    total = len(leads)
    sales = sum(q.status == 'venda_concluida' for q in leads)
    return {'Total de leads': total, 'Leads novos': sum(q.status == 'novo' for q in leads),
            'Orçamentos enviados': sum(q.status == 'orcamento_enviado' for q in leads),
            'Vendas concluídas': sales, 'Taxa de conversão': f'{sales / total * 100:.1f}%' if total else '0.0%'}
