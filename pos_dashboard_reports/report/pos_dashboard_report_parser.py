# -*- coding: utf-8 -*-
from odoo import models


class ReportPosDashboardDocument(models.AbstractModel):
    _name = "report.pos_dashboard_reports.report_pos_dashboard_document"
    _description = "POS Dashboard PDF Report Parser"

    def _get_report_values(self, docids, data=None):
        wizards = self.env["pos.dashboard.report.wizard"].browse(docids)
        engine = self.env["pos.dashboard.engine"]
        entries = []
        for wiz in wizards:
            ctx = wiz._report_context()
            report_data = engine.get_report(
                wiz.report_key, ctx["date_from"], ctx["date_to"],
                company_id=ctx["company_id"], config_ids=ctx["config_ids"],
                user_ids=ctx["user_ids"], limit=1000, offset=0,
            )
            entries.append({
                "wizard": wiz,
                "label": engine.REPORT_LABELS.get(wiz.report_key, wiz.report_key),
                "data": report_data,
            })
        return {
            "doc_ids": docids,
            "doc_model": "pos.dashboard.report.wizard",
            "docs": wizards,
            "entries": entries,
        }
