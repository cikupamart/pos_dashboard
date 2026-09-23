# -*- coding: utf-8 -*-
import io
import json
from datetime import datetime, timedelta

from odoo import http
from odoo.http import request


class PosDashboardController(http.Controller):

    # ------------------------------------------------------------------
    # JSON data feed used by the OWL dashboard (chart + table data only,
    # never the raw pos.order/pos.order.line recordsets).
    # ------------------------------------------------------------------
    @http.route("/pos_dashboard/data", type="json", auth="user")
    def dashboard_data(self, report_key, date_from, date_to, config_ids=None,
                        user_ids=None, limit=200, offset=0):
        engine = request.env["pos.dashboard.engine"]
        dt_from = "%s 00:00:00" % date_from
        dt_to = "%s 00:00:00" % (
            datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        return engine.get_report(
            report_key, dt_from, dt_to,
            company_id=request.env.company.id,
            config_ids=config_ids or None,
            user_ids=user_ids or None,
            limit=limit, offset=offset,
        )

    @http.route("/pos_dashboard/meta", type="json", auth="user")
    def dashboard_meta(self):
        engine = request.env["pos.dashboard.engine"]
        configs = request.env["pos.config"].search_read([], ["id", "name"])
        users = request.env["res.users"].search_read(
            [("groups_id", "in", [request.env.ref("point_of_sale.group_pos_user").id])],
            ["id", "name"],
        )
        reports = [
            {"key": k, "label": v} for k, v in engine.REPORT_LABELS.items()
        ]
        return {"reports": reports, "configs": configs, "users": users}

    # ------------------------------------------------------------------
    # Excel export - streams a single aggregated query result, same engine
    # used by the dashboard, so exporting is exactly as light as viewing.
    # ------------------------------------------------------------------
    @http.route("/pos_dashboard/export/xlsx", type="http", auth="user")
    def export_xlsx(self, wizard_id=None, report_key=None, date_from=None,
                     date_to=None, config_ids=None, user_ids=None, **kw):
        import xlsxwriter

        env = request.env
        if wizard_id:
            wiz = env["pos.dashboard.report.wizard"].browse(int(wizard_id))
            report_key = wiz.report_key
            ctx = wiz._report_context()
            dt_from, dt_to = ctx["date_from"], ctx["date_to"]
            company_id = ctx["company_id"]
            config_id_list = ctx["config_ids"]
            user_id_list = ctx["user_ids"]
        else:
            dt_from = "%s 00:00:00" % date_from
            dt_to = "%s 00:00:00" % (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            company_id = env.company.id
            config_id_list = json.loads(config_ids) if config_ids else None
            user_id_list = json.loads(user_ids) if user_ids else None

        engine = env["pos.dashboard.engine"]
        data = engine.get_report(
            report_key, dt_from, dt_to, company_id=company_id,
            config_ids=config_id_list, user_ids=user_id_list,
            limit=10000, offset=0,
        )
        label = engine.REPORT_LABELS.get(report_key, report_key)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(label[:31])
        bold = workbook.add_format({"bold": True, "bg_color": "#EFEFEF"})
        money = workbook.add_format({"num_format": "#,##0.00"})

        sheet.write(0, 0, label, bold)
        sheet.write(1, 0, "Periode: %s s/d %s" % (date_from or dt_from, date_to or dt_to))

        rows = data.get("rows")
        columns = data.get("columns")
        if columns and rows is not None:
            for c, (fname, flabel) in enumerate(columns):
                sheet.write(3, c, flabel, bold)
            for r, row in enumerate(rows, start=4):
                for c, (fname, flabel) in enumerate(columns):
                    value = row.get(fname)
                    if hasattr(value, "isoformat"):
                        value = value.isoformat()
                    if isinstance(value, (int, float)):
                        sheet.write_number(r, c, value, money)
                    else:
                        sheet.write(r, c, value if value is not None else "")
            for c in range(len(columns)):
                sheet.set_column(c, c, 20)
        elif data.get("kpi"):
            # KPI-style reports (mis. Direksi Report): tulis sebagai
            # beberapa blok tabel yang rapi, bukan dump JSON mentah.
            row = 3
            kpi = data["kpi"]
            sheet.write(row, 0, "Ringkasan", bold)
            row += 1
            for metric_label, value in (
                ("Jumlah Order", kpi.get("order_count")),
                ("Total Penjualan", kpi.get("revenue")),
                ("Pajak", kpi.get("tax")),
                ("Rata-rata / Transaksi", kpi.get("avg_basket")),
            ):
                sheet.write(row, 0, metric_label)
                sheet.write_number(row, 1, value or 0, money)
                row += 1
            row += 1

            trend = data.get("chart_trend")
            if trend and trend.get("labels"):
                sheet.write(row, 0, "Tren Penjualan Harian", bold)
                row += 1
                sheet.write(row, 0, "Tanggal", bold)
                sheet.write(row, 1, "Total", bold)
                row += 1
                values = trend["datasets"][0]["data"] if trend.get("datasets") else []
                for label, value in zip(trend["labels"], values):
                    sheet.write(row, 0, label)
                    sheet.write_number(row, 1, value, money)
                    row += 1
                row += 1

            category = data.get("chart_category")
            if category and category.get("labels"):
                sheet.write(row, 0, "Kategori Teratas", bold)
                row += 1
                sheet.write(row, 0, "Kategori", bold)
                sheet.write(row, 1, "Total", bold)
                row += 1
                values = category["datasets"][0]["data"] if category.get("datasets") else []
                for label, value in zip(category["labels"], values):
                    sheet.write(row, 0, label)
                    sheet.write_number(row, 1, value, money)
                    row += 1
                row += 1

            if data.get("top_kasir"):
                sheet.write(row, 0, "Top Kasir", bold)
                row += 1
                sheet.write(row, 0, "Kasir", bold)
                sheet.write(row, 1, "Total Penjualan", bold)
                row += 1
                for k in data["top_kasir"]:
                    sheet.write(row, 0, k.get("cashier"))
                    sheet.write_number(row, 1, float(k.get("revenue") or 0), money)
                    row += 1
                row += 1

            if data.get("top_category"):
                sheet.write(row, 0, "Top Kategori (dengan akun COA)", bold)
                row += 1
                sheet.write(row, 0, "Kategori", bold)
                sheet.write(row, 1, "Total", bold)
                row += 1
                for c in data["top_category"]:
                    sheet.write(row, 0, c.get("category_name"))
                    sheet.write_number(row, 1, float(c.get("amount_total") or 0), money)
                    row += 1

            sheet.set_column(0, 0, 28)
            sheet.set_column(1, 1, 18)
        else:
            sheet.write(3, 0, "Tidak ada data pada periode ini.")

        workbook.close()
        output.seek(0)
        filename = "%s.xlsx" % label.replace("/", "-")
        headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", 'attachment; filename="%s"' % filename),
        ]
        return request.make_response(output.read(), headers=headers)
