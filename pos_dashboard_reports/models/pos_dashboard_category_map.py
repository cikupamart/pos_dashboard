# -*- coding: utf-8 -*-
from odoo import fields, models


class PosDashboardCategoryMap(models.Model):
    """Memetakan product.category ke tipe laporan (Tenant / Rides / Bracelet /
    Ticket / Bundling) supaya modul ini bisa langsung dipakai tanpa harus
    menambah field custom di product.template.

    Tabel ini kecil (jumlah kategori produk), jadi aman dibaca penuh via ORM
    dan di-cache di Python saat dipakai untuk mengelompokkan hasil query SQL
    dari pos_order_line yang jumlah barisnya besar.
    """

    _name = "pos.dashboard.category.map"
    _description = "POS Dashboard - Category Report Mapping"
    _rec_name = "category_id"

    category_id = fields.Many2one(
        "product.category", required=True, ondelete="cascade", index=True
    )
    report_group = fields.Selection(
        [
            ("ticket", "Ticket"),
            ("tenant", "Tenant"),
            ("rides", "Rides"),
            ("bracelet", "Bracelet"),
            ("bundling", "Bundling"),
            ("other", "Lainnya"),
        ],
        required=True,
        default="other",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )

    _sql_constraints = [
        (
            "category_uniq",
            "unique(category_id, company_id)",
            "Kategori produk ini sudah dipetakan.",
        )
    ]
