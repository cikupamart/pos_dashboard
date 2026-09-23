# -*- coding: utf-8 -*-
"""
Mesin utama Dashboard & Reporting POS.

PRINSIP PERFORMA (WAJIB DIIKUTI SETIAP MENAMBAH LAPORAN BARU):
  1. Semua angka (SUM/COUNT/AVG) diambil lewat SQL agregat via
     self.env.cr.execute() -> tidak pernah melakukan browse()/search() atas
     seluruh baris pos_order_line / pos_order.
  2. Query WAJIB difilter tanggal (date_order) + company_id, dan selalu
     memakai kolom yang sudah ter-index (date_order, session_id, product_id,
     categ_id) sebagai syarat JOIN/WHERE.
  3. Kolom yang bertipe "translatable" (name pada product.template,
     product.category, account.journal, account.account, pos.config, dsb)
     di Odoo 16 disimpan sebagai JSONB, jadi TIDAK diambil lewat SQL mentah.
     Nama-nama itu diambil belakangan lewat ORM hanya untuk kumpulan ID hasil
     agregasi (jumlahnya kecil: puluhan/ratusan produk atau kategori), bukan
     untuk tiap baris transaksi.
  4. Setiap laporan berbasis daftar (bukan agregat) WAJIB memakai
     LIMIT/OFFSET (default 200 baris per halaman).
"""
from collections import defaultdict

from odoo import api, models


DEFAULT_LIMIT = 200
DONE_STATES = ("paid", "done", "invoiced")


class PosDashboardEngine(models.AbstractModel):
    _name = "pos.dashboard.engine"
    _description = "POS Dashboard - Lightweight Reporting Engine"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _names(self, model, ids):
        """Ambil display_name untuk sekumpulan ID kecil lewat ORM.
        Dipakai supaya field translatable (jsonb) tidak pernah dibaca lewat
        SQL mentah."""
        ids = [i for i in set(ids) if i]
        if not ids:
            return {}
        recs = self.env[model].sudo().browse(ids).exists()
        return {r.id: r.display_name for r in recs}

    def _category_map(self):
        """category_id -> report_group, dibaca sekali (tabel kecil)."""
        maps = self.env["pos.dashboard.category.map"].sudo().search([])
        result = defaultdict(lambda: "other")
        for m in maps:
            result[m.category_id.id] = m.report_group
        return result

    def _category_ids_for_group(self, group):
        maps = self.env["pos.dashboard.category.map"].sudo().search(
            [("report_group", "=", group)]
        )
        return maps.mapped("category_id").ids

    def _build_where(self, date_from, date_to, company_id=None,
                      config_ids=None, user_ids=None, alias_order="o",
                      alias_session="s"):
        where = [
            "%s.date_order >= %%s" % alias_order,
            "%s.date_order < %%s" % alias_order,
            "%s.state = ANY(%%s)" % alias_order,
        ]
        params = [date_from, date_to, list(DONE_STATES)]
        if company_id:
            where.append("%s.company_id = %%s" % alias_order)
            params.append(company_id)
        if config_ids:
            where.append("%s.config_id = ANY(%%s)" % alias_session)
            params.append(list(config_ids))
        if user_ids:
            where.append("%s.user_id = ANY(%%s)" % alias_order)
            params.append(list(user_ids))
        return " AND ".join(where), params

    def _execute(self, sql, params):
        self.env.cr.execute(sql, params)
        cols = [d[0] for d in self.env.cr.description]
        return [dict(zip(cols, row)) for row in self.env.cr.fetchall()]

    # ------------------------------------------------------------------
    # Shared aggregators reused by several reports (product level / order
    # level) so we don't repeat near-identical SQL 6 times.
    # ------------------------------------------------------------------
    def _product_group_report(self, date_from, date_to, company_id=None,
                               config_ids=None, user_ids=None,
                               category_ids=None, limit=DEFAULT_LIMIT,
                               offset=0):
        """Group pos_order_line by product, optionally restricted to a set
        of product.category ids (used for Sale/Ticket/Tenant/Rides/Bracelet
        reports). One aggregated SQL query, then names resolved via ORM for
        the resulting (small) set of products."""
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        extra = ""
        if category_ids:
            extra = " AND pt.categ_id = ANY(%s)"
            params.append(list(category_ids))

        sql = """
            SELECT l.product_id AS product_id,
                   pt.categ_id AS categ_id,
                   SUM(l.qty) AS qty,
                   SUM(l.price_subtotal) AS amount_untaxed,
                   SUM(l.price_subtotal_incl) AS amount_total,
                   COUNT(DISTINCT l.order_id) AS order_count
              FROM pos_order_line l
              JOIN pos_order o ON o.id = l.order_id
              JOIN pos_session s ON s.id = o.session_id
              JOIN product_product pp ON pp.id = l.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %s %s
          GROUP BY l.product_id, pt.categ_id
          ORDER BY amount_total DESC
             LIMIT %%s OFFSET %%s
        """ % (where, extra)
        params += [limit, offset]
        rows = self._execute(sql, params)

        prod_names = self._names("product.product", [r["product_id"] for r in rows])
        categ_names = self._names("product.category", [r["categ_id"] for r in rows])
        for r in rows:
            r["product_name"] = prod_names.get(r["product_id"], "?")
            r["category_name"] = categ_names.get(r["categ_id"], "?")
        return rows

    def _transaction_group_report(self, date_from, date_to, company_id=None,
                                   config_ids=None, user_ids=None,
                                   category_ids=None, limit=DEFAULT_LIMIT,
                                   offset=0):
        """Order-level list restricted to orders that contain at least one
        line whose product belongs to `category_ids` (used for Transaction
        Ticket Report & Bundling Transaction Report)."""
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        cat_filter = ""
        if category_ids:
            cat_filter = """
              AND EXISTS (
                    SELECT 1 FROM pos_order_line xl
                    JOIN product_product xpp ON xpp.id = xl.product_id
                    JOIN product_template xpt ON xpt.id = xpp.product_tmpl_id
                   WHERE xl.order_id = o.id AND xpt.categ_id = ANY(%s))
            """
            params.append(list(category_ids))

        sql = """
            SELECT o.id AS order_id, o.pos_reference AS reference,
                   o.date_order AS date_order, o.user_id AS user_id,
                   s.config_id AS config_id, o.amount_total AS amount_total,
                   o.amount_tax AS amount_tax,
                   (SELECT COUNT(*) FROM pos_order_line yl WHERE yl.order_id = o.id) AS line_count
              FROM pos_order o
              JOIN pos_session s ON s.id = o.session_id
             WHERE %s %s
          ORDER BY o.date_order DESC
             LIMIT %%s OFFSET %%s
        """ % (where, cat_filter)
        params += [limit, offset]
        rows = self._execute(sql, params)

        user_names = self._names("res.users", [r["user_id"] for r in rows])
        config_names = self._names("pos.config", [r["config_id"] for r in rows])
        for r in rows:
            r["cashier"] = user_names.get(r["user_id"], "?")
            r["pos"] = config_names.get(r["config_id"], "?")
        return rows

    # ------------------------------------------------------------------
    # 1. Reporting Orders
    # ------------------------------------------------------------------
    def report_reporting_orders(self, date_from, date_to, company_id=None,
                                 config_ids=None, user_ids=None,
                                 limit=DEFAULT_LIMIT, offset=0, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        sql = """
            SELECT o.id AS order_id, o.pos_reference AS reference,
                   o.date_order AS date_order, o.user_id AS user_id,
                   o.partner_id AS partner_id, s.config_id AS config_id,
                   o.amount_total AS amount_total, o.amount_tax AS amount_tax,
                   o.state AS state
              FROM pos_order o
              JOIN pos_session s ON s.id = o.session_id
             WHERE %s
          ORDER BY o.date_order DESC
             LIMIT %%s OFFSET %%s
        """ % where
        params += [limit, offset]
        rows = self._execute(sql, params)

        user_names = self._names("res.users", [r["user_id"] for r in rows])
        config_names = self._names("pos.config", [r["config_id"] for r in rows])
        partner_names = self._names("res.partner", [r["partner_id"] for r in rows])
        for r in rows:
            r["cashier"] = user_names.get(r["user_id"], "?")
            r["pos"] = config_names.get(r["config_id"], "?")
            r["customer"] = partner_names.get(r["partner_id"], "-")

        chart_sql = """
            SELECT date_trunc('day', o.date_order)::date AS day,
                   COUNT(*) AS order_count, SUM(o.amount_total) AS total
              FROM pos_order o JOIN pos_session s ON s.id = o.session_id
             WHERE %s
          GROUP BY 1 ORDER BY 1
        """ % where
        chart_rows = self._execute(chart_sql, params[:-2])
        chart = {
            "labels": [r["day"].strftime("%d-%m") for r in chart_rows],
            "datasets": [
                {"label": "Jumlah Order", "data": [r["order_count"] for r in chart_rows]},
                {"label": "Total Penjualan", "data": [float(r["total"]) for r in chart_rows]},
            ],
        }
        return {
            "columns": [
                ("reference", "No. Order"), ("date_order", "Tanggal"),
                ("pos", "POS"), ("cashier", "Kasir"), ("customer", "Pelanggan"),
                ("amount_total", "Total"), ("amount_tax", "Pajak"), ("state", "Status"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # Internal helper: generic KPI overview (revenue/tax/trend/top category),
    # reused by the Direksi report. Not exposed as its own report anymore -
    # see report_pos_payment_analysis below for the payment-focused report.
    # ------------------------------------------------------------------
    def _overview_kpis(self, date_from, date_to, company_id=None,
                        config_ids=None, user_ids=None, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        kpi_sql = """
            SELECT COUNT(*) AS order_count, COALESCE(SUM(o.amount_total),0) AS revenue,
                   COALESCE(SUM(o.amount_tax),0) AS tax,
                   COALESCE(AVG(o.amount_total),0) AS avg_basket
              FROM pos_order o JOIN pos_session s ON s.id = o.session_id
             WHERE %s
        """ % where
        kpi = self._execute(kpi_sql, params)[0]

        trend_sql = """
            SELECT date_trunc('day', o.date_order)::date AS day,
                   SUM(o.amount_total) AS total
              FROM pos_order o JOIN pos_session s ON s.id = o.session_id
             WHERE %s GROUP BY 1 ORDER BY 1
        """ % where
        trend = self._execute(trend_sql, params)

        top_categ_sql = """
            SELECT pt.categ_id AS categ_id, SUM(l.price_subtotal_incl) AS total
              FROM pos_order_line l
              JOIN pos_order o ON o.id = l.order_id
              JOIN pos_session s ON s.id = o.session_id
              JOIN product_product pp ON pp.id = l.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %s
          GROUP BY pt.categ_id ORDER BY total DESC LIMIT 8
        """ % where
        top_categ = self._execute(top_categ_sql, params)
        categ_names = self._names("product.category", [r["categ_id"] for r in top_categ])

        return {
            "kpi": {
                "order_count": kpi["order_count"],
                "revenue": float(kpi["revenue"]),
                "tax": float(kpi["tax"]),
                "avg_basket": float(kpi["avg_basket"]),
            },
            "chart_trend": {
                "labels": [r["day"].strftime("%d-%m") for r in trend],
                "datasets": [{"label": "Penjualan", "data": [float(r["total"]) for r in trend]}],
            },
            "chart_category": {
                "labels": [categ_names.get(r["categ_id"], "?") for r in top_categ],
                "datasets": [{"label": "Kategori", "data": [float(r["total"]) for r in top_categ]}],
            },
        }

    # ------------------------------------------------------------------
    # 2. POS Payment Analysis - breakdown per metode pembayaran: jumlah
    # transaksi, total, rata-rata per transaksi, dan share (%) terhadap
    # total penerimaan pada periode terpilih. Bentuknya tabel (columns/rows)
    # sehingga export Excel/PDF-nya rapi (sebelumnya laporan ini berbentuk
    # ringkasan KPI saja, yang membuat export Excel-nya tidak sesuai format
    # tabel).
    # ------------------------------------------------------------------
    def report_pos_payment_analysis(self, date_from, date_to, company_id=None,
                                     config_ids=None, user_ids=None, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        sql = """
            SELECT pm.id AS method_id, pm.journal_id AS journal_id,
                   pm.is_cash_count AS is_cash,
                   COUNT(*) AS txn_count,
                   SUM(pay.amount) AS total_amount,
                   AVG(pay.amount) AS avg_amount
              FROM pos_payment pay
              JOIN pos_order o ON o.id = pay.pos_order_id
              JOIN pos_session s ON s.id = o.session_id
              JOIN pos_payment_method pm ON pm.id = pay.payment_method_id
             WHERE %s
          GROUP BY pm.id, pm.journal_id, pm.is_cash_count
          ORDER BY total_amount DESC
        """ % where
        rows = self._execute(sql, params)

        method_names = self._names("pos.payment.method", [r["method_id"] for r in rows])
        journal_names = self._names("account.journal", [r["journal_id"] for r in rows])
        grand_total = sum(float(r["total_amount"] or 0) for r in rows) or 1.0
        for r in rows:
            r["method"] = method_names.get(r["method_id"], "?")
            r["journal"] = journal_names.get(r["journal_id"], "-")
            r["payment_type"] = "Tunai" if r["is_cash"] else "Non-Tunai"
            r["total_amount"] = float(r["total_amount"] or 0)
            r["avg_amount"] = float(r["avg_amount"] or 0)
            r["share_pct"] = round(r["total_amount"] / grand_total * 100, 2)

        chart = {
            "labels": [r["method"] for r in rows],
            "datasets": [{"label": "Total per Metode Pembayaran",
                          "data": [r["total_amount"] for r in rows]}],
        }
        return {
            "columns": [
                ("method", "Metode Pembayaran"), ("payment_type", "Tipe"),
                ("journal", "Jurnal"), ("txn_count", "Jumlah Transaksi"),
                ("total_amount", "Total"), ("avg_amount", "Rata-rata / Transaksi"),
                ("share_pct", "% dari Total"),
            ],
            "rows": rows, "chart": chart,
        }


    # ------------------------------------------------------------------
    def report_sales_detail(self, date_from, date_to, company_id=None,
                             config_ids=None, user_ids=None,
                             limit=DEFAULT_LIMIT, offset=0, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        sql = """
            SELECT l.id AS line_id, o.pos_reference AS reference,
                   o.date_order AS date_order, o.user_id AS user_id,
                   l.product_id AS product_id, l.qty AS qty,
                   l.price_unit AS price_unit, l.discount AS discount,
                   l.price_subtotal AS amount_untaxed,
                   l.price_subtotal_incl AS amount_total
              FROM pos_order_line l
              JOIN pos_order o ON o.id = l.order_id
              JOIN pos_session s ON s.id = o.session_id
             WHERE %s
          ORDER BY o.date_order DESC
             LIMIT %%s OFFSET %%s
        """ % where
        params += [limit, offset]
        rows = self._execute(sql, params)
        prod_names = self._names("product.product", [r["product_id"] for r in rows])
        user_names = self._names("res.users", [r["user_id"] for r in rows])
        for r in rows:
            r["product_name"] = prod_names.get(r["product_id"], "?")
            r["cashier"] = user_names.get(r["user_id"], "?")
        return {
            "columns": [
                ("reference", "No. Order"), ("date_order", "Tanggal"),
                ("cashier", "Kasir"), ("product_name", "Produk"), ("qty", "Qty"),
                ("price_unit", "Harga"), ("discount", "Disc %"),
                ("amount_untaxed", "Subtotal"), ("amount_total", "Total"),
            ],
            "rows": rows, "chart": None,
        }

    # ------------------------------------------------------------------
    # 4. Sale Report (per produk, semua kategori)
    # ------------------------------------------------------------------
    def report_sale_report(self, date_from, date_to, **kw):
        rows = self._product_group_report(date_from, date_to, **kw)
        chart = {
            "labels": [r["product_name"] for r in rows[:10]],
            "datasets": [{"label": "Penjualan", "data": [float(r["amount_total"]) for r in rows[:10]]}],
        }
        return {
            "columns": [
                ("product_name", "Produk"), ("category_name", "Kategori"),
                ("qty", "Qty Terjual"), ("amount_untaxed", "Subtotal"),
                ("amount_total", "Total"), ("order_count", "Jumlah Transaksi"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 5. Sale per Kasir Report
    # ------------------------------------------------------------------
    def report_sale_per_kasir(self, date_from, date_to, company_id=None,
                               config_ids=None, user_ids=None, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        sql = """
            SELECT o.user_id AS user_id, COUNT(*) AS order_count,
                   SUM(o.amount_total) AS revenue, SUM(o.amount_tax) AS tax,
                   AVG(o.amount_total) AS avg_basket
              FROM pos_order o JOIN pos_session s ON s.id = o.session_id
             WHERE %s
          GROUP BY o.user_id ORDER BY revenue DESC
        """ % where
        rows = self._execute(sql, params)
        names = self._names("res.users", [r["user_id"] for r in rows])
        for r in rows:
            r["cashier"] = names.get(r["user_id"], "?")
        chart = {
            "labels": [r["cashier"] for r in rows],
            "datasets": [{"label": "Penjualan per Kasir", "data": [float(r["revenue"]) for r in rows]}],
        }
        return {
            "columns": [
                ("cashier", "Kasir"), ("order_count", "Jumlah Order"),
                ("revenue", "Total Penjualan"), ("tax", "Pajak"),
                ("avg_basket", "Rata-rata / Transaksi"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 6. Sale Ticket Report
    # ------------------------------------------------------------------
    def report_sale_ticket(self, date_from, date_to, **kw):
        cats = self._category_ids_for_group("ticket")
        rows = self._product_group_report(date_from, date_to, category_ids=cats, **kw)
        chart = {
            "labels": [r["product_name"] for r in rows[:10]],
            "datasets": [{"label": "Tiket Terjual", "data": [float(r["qty"]) for r in rows[:10]]}],
        }
        return {
            "columns": [
                ("product_name", "Jenis Tiket"), ("qty", "Qty"),
                ("amount_untaxed", "Subtotal"), ("amount_total", "Total"),
                ("order_count", "Jumlah Transaksi"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 7. Sale Ticket Tax Report
    # ------------------------------------------------------------------
    def report_sale_ticket_tax(self, date_from, date_to, **kw):
        cats = self._category_ids_for_group("ticket")
        rows = self._product_group_report(date_from, date_to, category_ids=cats, **kw)
        product_ids = [r["product_id"] for r in rows]
        products = self.env["product.product"].sudo().browse(product_ids)
        tax_by_product = {p.id: p.taxes_id.mapped("name") for p in products}
        for r in rows:
            r["tax_amount"] = float(r["amount_total"]) - float(r["amount_untaxed"])
            r["tax_names"] = ", ".join(tax_by_product.get(r["product_id"], [])) or "-"
        chart = {
            "labels": [r["product_name"] for r in rows[:10]],
            "datasets": [{"label": "Pajak", "data": [r["tax_amount"] for r in rows[:10]]}],
        }
        return {
            "columns": [
                ("product_name", "Jenis Tiket"), ("tax_names", "Tarif Pajak"),
                ("amount_untaxed", "DPP (Subtotal)"), ("tax_amount", "Pajak"),
                ("amount_total", "Total Termasuk Pajak"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 8/9/10. Tenant / Rides / Bracelet (sama pola, beda kategori)
    # ------------------------------------------------------------------
    def report_sale_tenant(self, date_from, date_to, **kw):
        return self._grouped_named("tenant", "Tenant", date_from, date_to, **kw)

    def report_sale_rides(self, date_from, date_to, **kw):
        return self._grouped_named("rides", "Wahana", date_from, date_to, **kw)

    def report_bracelet(self, date_from, date_to, **kw):
        return self._grouped_named("bracelet", "Gelang", date_from, date_to, **kw)

    def _grouped_named(self, group, label, date_from, date_to, **kw):
        cats = self._category_ids_for_group(group)
        rows = self._product_group_report(date_from, date_to, category_ids=cats, **kw)
        chart = {
            "labels": [r["product_name"] for r in rows[:10]],
            "datasets": [{"label": label, "data": [float(r["amount_total"]) for r in rows[:10]]}],
        }
        return {
            "columns": [
                ("product_name", label), ("qty", "Qty"),
                ("amount_untaxed", "Subtotal"), ("amount_total", "Total"),
                ("order_count", "Jumlah Transaksi"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 11. Transaction Ticket Report (level transaksi)
    # ------------------------------------------------------------------
    def report_transaction_ticket(self, date_from, date_to, **kw):
        cats = self._category_ids_for_group("ticket")
        rows = self._transaction_group_report(date_from, date_to, category_ids=cats, **kw)
        chart = {
            "labels": [r["reference"] for r in rows[:15]],
            "datasets": [{"label": "Total Transaksi", "data": [float(r["amount_total"]) for r in rows[:15]]}],
        }
        return {
            "columns": [
                ("reference", "No. Struk"), ("date_order", "Tanggal"),
                ("pos", "POS"), ("cashier", "Kasir"), ("line_count", "Jumlah Item"),
                ("amount_total", "Total"), ("amount_tax", "Pajak"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 12. Summary Product Category / COA Report
    # ------------------------------------------------------------------
    def report_summary_category_coa(self, date_from, date_to, company_id=None,
                                     config_ids=None, user_ids=None, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        sql = """
            SELECT pt.categ_id AS categ_id, SUM(l.qty) AS qty,
                   SUM(l.price_subtotal) AS amount_untaxed,
                   SUM(l.price_subtotal_incl) AS amount_total
              FROM pos_order_line l
              JOIN pos_order o ON o.id = l.order_id
              JOIN pos_session s ON s.id = o.session_id
              JOIN product_product pp ON pp.id = l.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %s
          GROUP BY pt.categ_id ORDER BY amount_total DESC
        """ % where
        rows = self._execute(sql, params)
        categs = self.env["product.category"].sudo().browse([r["categ_id"] for r in rows])
        acc_by_categ = {}
        for c in categs:
            account = c.property_account_income_categ_id
            acc_by_categ[c.id] = "%s %s" % (account.code or "", account.name or "-") if account else "-"
        categ_names = {c.id: c.display_name for c in categs}
        for r in rows:
            r["category_name"] = categ_names.get(r["categ_id"], "?")
            r["coa_account"] = acc_by_categ.get(r["categ_id"], "-")
        chart = {
            "labels": [r["category_name"] for r in rows],
            "datasets": [{"label": "Penjualan per Kategori", "data": [float(r["amount_total"]) for r in rows]}],
        }
        return {
            "columns": [
                ("category_name", "Kategori Produk"), ("coa_account", "Akun COA"),
                ("qty", "Qty"), ("amount_untaxed", "Subtotal"), ("amount_total", "Total"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 13. Direksi Report (Executive Summary)
    # ------------------------------------------------------------------
    def report_direksi(self, date_from, date_to, company_id=None,
                        config_ids=None, user_ids=None, **kw):
        analisis = self._overview_kpis(
            date_from, date_to, company_id=company_id,
            config_ids=config_ids, user_ids=user_ids)
        kasir = self.report_sale_per_kasir(
            date_from, date_to, company_id=company_id,
            config_ids=config_ids, user_ids=user_ids)
        categ = self.report_summary_category_coa(
            date_from, date_to, company_id=company_id,
            config_ids=config_ids, user_ids=user_ids)
        return {
            "kpi": analisis["kpi"],
            "chart_trend": analisis["chart_trend"],
            "chart_category": analisis["chart_category"],
            "top_kasir": kasir["rows"][:5],
            "top_category": categ["rows"][:5],
        }

    # ------------------------------------------------------------------
    # 14. Sale Order Report (per sesi kasir)
    # ------------------------------------------------------------------
    def report_sale_order(self, date_from, date_to, company_id=None,
                           config_ids=None, user_ids=None,
                           limit=DEFAULT_LIMIT, offset=0, **kw):
        where = ["s.stop_at >= %s OR s.stop_at IS NULL", "s.start_at < %s"]
        params = [date_from, date_to]
        if company_id:
            where.append("s.company_id = %s")
            params.append(company_id)
        if config_ids:
            where.append("s.config_id = ANY(%s)")
            params.append(list(config_ids))
        if user_ids:
            where.append("s.user_id = ANY(%s)")
            params.append(list(user_ids))
        sql = """
            SELECT s.id AS session_id, s.name AS session_name, s.config_id AS config_id,
                   s.user_id AS user_id, s.start_at AS start_at, s.stop_at AS stop_at,
                   (SELECT COUNT(*) FROM pos_order o WHERE o.session_id = s.id AND o.state = ANY(%%s)) AS order_count,
                   (SELECT COALESCE(SUM(o.amount_total),0) FROM pos_order o WHERE o.session_id = s.id AND o.state = ANY(%%s)) AS revenue,
                   (SELECT COALESCE(SUM(o.amount_tax),0) FROM pos_order o WHERE o.session_id = s.id AND o.state = ANY(%%s)) AS tax
              FROM pos_session s
             WHERE %s
          ORDER BY s.start_at DESC
             LIMIT %%s OFFSET %%s
        """ % " AND ".join(where)
        params = [list(DONE_STATES), list(DONE_STATES), list(DONE_STATES)] + params + [limit, offset]
        rows = self._execute(sql, params)
        config_names = self._names("pos.config", [r["config_id"] for r in rows])
        user_names = self._names("res.users", [r["user_id"] for r in rows])
        for r in rows:
            r["pos"] = config_names.get(r["config_id"], "?")
            r["cashier"] = user_names.get(r["user_id"], "?")
        return {
            "columns": [
                ("session_name", "Sesi"), ("pos", "POS"), ("cashier", "Kasir"),
                ("start_at", "Buka"), ("stop_at", "Tutup"),
                ("order_count", "Jumlah Order"), ("revenue", "Total Penjualan"), ("tax", "Pajak"),
            ],
            "rows": rows, "chart": None,
        }

    # ------------------------------------------------------------------
    # 15. Accounting Report (berdasarkan metode pembayaran -> jurnal)
    # ------------------------------------------------------------------
    def report_accounting(self, date_from, date_to, company_id=None,
                           config_ids=None, user_ids=None, **kw):
        where, params = self._build_where(date_from, date_to, company_id,
                                           config_ids, user_ids)
        sql = """
            SELECT pm.journal_id AS journal_id, pm.id AS method_id,
                   COUNT(*) AS payment_count, SUM(pay.amount) AS total
              FROM pos_payment pay
              JOIN pos_order o ON o.id = pay.pos_order_id
              JOIN pos_session s ON s.id = o.session_id
              JOIN pos_payment_method pm ON pm.id = pay.payment_method_id
             WHERE %s
          GROUP BY pm.journal_id, pm.id ORDER BY total DESC
        """ % where
        rows = self._execute(sql, params)
        journal_names = self._names("account.journal", [r["journal_id"] for r in rows])
        method_names = self._names("pos.payment.method", [r["method_id"] for r in rows])
        for r in rows:
            r["journal"] = journal_names.get(r["journal_id"], "-")
            r["method"] = method_names.get(r["method_id"], "?")
        chart = {
            "labels": [r["journal"] for r in rows],
            "datasets": [{"label": "Total per Jurnal", "data": [float(r["total"]) for r in rows]}],
        }
        return {
            "columns": [
                ("method", "Metode Pembayaran"), ("journal", "Jurnal Akuntansi"),
                ("payment_count", "Jumlah Pembayaran"), ("total", "Total"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # 16. Bundling Transaction Report (level transaksi)
    # ------------------------------------------------------------------
    def report_bundling_transaction(self, date_from, date_to, **kw):
        cats = self._category_ids_for_group("bundling")
        rows = self._transaction_group_report(date_from, date_to, category_ids=cats, **kw)
        chart = {
            "labels": [r["reference"] for r in rows[:15]],
            "datasets": [{"label": "Total Bundling", "data": [float(r["amount_total"]) for r in rows[:15]]}],
        }
        return {
            "columns": [
                ("reference", "No. Struk"), ("date_order", "Tanggal"),
                ("pos", "POS"), ("cashier", "Kasir"), ("line_count", "Jumlah Item"),
                ("amount_total", "Total"), ("amount_tax", "Pajak"),
            ],
            "rows": rows, "chart": chart,
        }

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------
    REPORT_METHODS = {
        "reporting_orders": "report_reporting_orders",
        "pos_payment_analysis": "report_pos_payment_analysis",
        "sales_detail": "report_sales_detail",
        "sale_report": "report_sale_report",
        "sale_per_kasir": "report_sale_per_kasir",
        "sale_ticket": "report_sale_ticket",
        "sale_ticket_tax": "report_sale_ticket_tax",
        "sale_tenant": "report_sale_tenant",
        "sale_rides": "report_sale_rides",
        "bracelet": "report_bracelet",
        "transaction_ticket": "report_transaction_ticket",
        "summary_category_coa": "report_summary_category_coa",
        "direksi": "report_direksi",
        "sale_order": "report_sale_order",
        "accounting": "report_accounting",
        "bundling_transaction": "report_bundling_transaction",
    }

    REPORT_LABELS = {
        "reporting_orders": "Reporting Orders",
        "pos_payment_analysis": "POS Payment Analysis",
        "sales_detail": "Sales Detail",
        "sale_report": "Sale Report",
        "sale_per_kasir": "Sale per Kasir Report",
        "sale_ticket": "Sale Ticket Report",
        "sale_ticket_tax": "Sale Ticket Tax Report",
        "sale_tenant": "Sale Tenant Report",
        "sale_rides": "Sale Rides Report",
        "bracelet": "Bracelet Report",
        "transaction_ticket": "Transaction Ticket Report",
        "summary_category_coa": "Summary Product Category / COA Report",
        "direksi": "Direksi Report",
        "sale_order": "Sale Order Report",
        "accounting": "Accounting Report",
        "bundling_transaction": "Bundling Transaction Report",
    }

    @api.model
    def get_report(self, report_key, date_from, date_to, company_id=None,
                    config_ids=None, user_ids=None, limit=DEFAULT_LIMIT, offset=0):
        method_name = self.REPORT_METHODS.get(report_key)
        if not method_name:
            return {"error": "Laporan tidak dikenal: %s" % report_key}
        method = getattr(self, method_name)
        return method(
            date_from, date_to, company_id=company_id,
            config_ids=config_ids, user_ids=user_ids, limit=limit, offset=offset,
        )
