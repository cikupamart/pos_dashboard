# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


REPORT_SELECTION = [
    ("reporting_orders", "Reporting Orders"),
    ("pos_payment_analysis", "POS Payment Analysis"),
    ("sales_detail", "Sales Detail"),
    ("sale_report", "Sale Report"),
    ("sale_per_kasir", "Sale per Kasir Report"),
    ("sale_ticket", "Sale Ticket Report"),
    ("sale_ticket_tax", "Sale Ticket Tax Report"),
    ("sale_tenant", "Sale Tenant Report"),
    ("sale_rides", "Sale Rides Report"),
    ("bracelet", "Bracelet Report"),
    ("transaction_ticket", "Transaction Ticket Report"),
    ("summary_category_coa", "Summary Product Category / COA Report"),
    ("direksi", "Direksi Report"),
    ("sale_order", "Sale Order Report"),
    ("accounting", "Accounting Report"),
    ("bundling_transaction", "Bundling Transaction Report"),
]


class PosDashboardReportWizard(models.TransientModel):
    _name = "pos.dashboard.report.wizard"
    _description = "POS Dashboard - Filter & Export Laporan"

    report_key = fields.Selection(REPORT_SELECTION, required=True,
                                   default="direksi")
    date_from = fields.Date(required=True,
                             default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.today)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    config_ids = fields.Many2many("pos.config", string="POS (kosongkan = semua)")
    user_ids = fields.Many2many("res.users", string="Kasir (kosongkan = semua)")

    def _report_context(self):
        self.ensure_one()
        return dict(
            date_from="%s 00:00:00" % self.date_from.strftime("%Y-%m-%d"),
            date_to="%s 00:00:00" % (self.date_to + timedelta(days=1)).strftime("%Y-%m-%d"),
            company_id=self.company_id.id,
            config_ids=self.config_ids.ids or None,
            user_ids=self.user_ids.ids or None,
        )

    def action_view_dashboard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "pos_dashboard_client_action",
            "name": dict(REPORT_SELECTION).get(self.report_key),
            "params": {
                "report_key": self.report_key,
                "date_from": self.date_from.strftime("%Y-%m-%d"),
                "date_to": self.date_to.strftime("%Y-%m-%d"),
                "config_ids": self.config_ids.ids,
                "user_ids": self.user_ids.ids,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            "pos_dashboard_reports.action_report_pos_dashboard_pdf"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        url = (
            "/pos_dashboard/export/xlsx?wizard_id=%s" % self.id
        )
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "self",
        }
