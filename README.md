# POS Dashboard & Reporting Suite (Odoo 16)

Modul dashboard + 16 laporan Point of Sale, dibangun supaya **ringan**:
semua angka diambil lewat SQL agregat (`GROUP BY` / `SUM` langsung di
PostgreSQL), selalu difilter tanggal + company, dan hanya kolom yang
dibutuhkan yang dibaca — tidak pernah `browse()`/`search()` seluruh tabel
`pos_order` / `pos_order_line`. Nama-nama yang tersimpan sebagai field
translatable (produk, kategori, jurnal, dll — disimpan JSONB di Odoo 16)
diambil lewat ORM hanya untuk ID hasil agregasi (jumlahnya kecil), bukan
per baris transaksi. Lihat komentar di `models/pos_dashboard_engine.py`.

## Instalasi
1. Salin folder `pos_dashboard_reports` ke `addons_path` server Odoo 16.
2. Update Apps List, lalu install module **POS Dashboard & Reporting Suite**.
3. Modul depend ke `point_of_sale`, `account`, `web`.

## Langkah setelah install
1. Buka **POS Dashboard > Konfigurasi > Mapping Kategori Laporan**
   (butuh grup *Dashboard Manager*). Petakan `product.category` yang
   relevan ke tipe: Tenant, Rides, Bracelet, Ticket, atau Bundling.
   Laporan **Sale Tenant / Sale Rides / Bracelet / Sale Ticket /
   Sale Ticket Tax / Transaction Ticket / Bundling Transaction** akan
   otomatis terisi berdasarkan mapping ini — tidak perlu field custom di
   produk.
2. Beri user akses ke grup **Dashboard User** (POS Dashboard > pengaturan
   user) supaya menu & laporan muncul.

## Menu
- **POS Dashboard > Dashboard** — dashboard interaktif (OWL + Chart.js),
  bisa ganti laporan/filter tanggal/POS langsung dari dropdown, lalu
  export Excel dari tombol di toolbar.
- **POS Dashboard > Laporan** — wizard filter (tanggal, POS, kasir) untuk
  membuka dashboard laporan tertentu, cetak PDF, atau export Excel.

## 16 Laporan
1. Reporting Orders — daftar order (paginated).
2. POS Payment Analysis — breakdown per metode pembayaran (jumlah
   transaksi, total, rata-rata, % dari total penerimaan).
3. Sales Detail — level baris transaksi.
4. Sale Report — agregat per produk.
5. Sale per Kasir Report.
6. Sale Ticket Report.
7. Sale Ticket Tax Report (pajak per jenis tiket, berdasarkan tax yang
   dikonfigurasi di produk).
8. Sale Tenant Report.
9. Sale Rides Report.
10. Bracelet Report.
11. Transaction Ticket Report — level transaksi (bukan produk).
12. Summary Product Category / COA Report — termasuk akun income (COA)
    dari `product.category`.
13. Direksi Report — ringkasan eksekutif (KPI + top kasir + top kategori).
14. Sale Order Report — per sesi kasir (buka/tutup, total, pajak).
15. Accounting Report — total per metode pembayaran & jurnal akuntansi.
16. Bundling Transaction Report — level transaksi untuk kategori Bundling.

## Catatan Desain / Keterbatasan yang Perlu Disesuaikan
- **Tenant / Rides / Bracelet / Ticket / Bundling** diasumsikan sebagai
  *kategori produk*, bukan field baru — sesuaikan mapping di
  Konfigurasi. Jika di sistem Anda konsepnya berbeda (mis. field custom
  di `pos.order.line`), sesuaikan query di
  `models/pos_dashboard_engine.py` (`_product_group_report` /
  `_transaction_group_report`).
- **Accounting Report** dihitung dari `pos.payment` → `pos.payment.method`
  → `account.journal` (total per metode/jurnal), bukan buku besar penuh.
  Jika butuh laporan neraca/laba-rugi, gunakan modul Accounting Odoo
  standar; laporan ini hanya rekap kas/rekonsiliasi kasir.
- **Sale Ticket Tax Report** memakai pajak yang dikonfigurasi di produk
  (`product.taxes_id`), karena `pos.order.line.tax_ids` adalah field
  many2many yang sengaja dihindari dari SQL mentah (nama tabel relasi
  m2m bisa berubah antar versi/patch) — jumlah barisnya kecil (per
  produk) sehingga dibaca lewat ORM, bukan per baris transaksi, jadi
  tetap ringan.
- Field `tax_ids`/nama translatable lain tetap diambil lewat ORM untuk
  himpunan ID kecil, sesuai prinsip performa di atas.

## Export
- **Excel**: `xlsxwriter`, endpoint `/pos_dashboard/export/xlsx` — memakai
  query yang sama dengan dashboard (limit lebih besar, default 10.000
  baris).
- **PDF**: QWeb report `pos_dashboard_reports.report_pos_dashboard_document`,
  datanya diambil oleh `report/pos_dashboard_report_parser.py` lewat
  engine yang sama.

## Struktur Kode
```
models/pos_dashboard_engine.py       -> mesin agregasi SQL untuk 16 laporan
models/pos_dashboard_category_map.py -> mapping kategori -> tipe laporan
wizard/pos_dashboard_wizard.py       -> filter tanggal/POS/kasir + tombol aksi
controllers/main.py                  -> JSON feed dashboard + export Excel
report/                              -> parser & template PDF
static/src/                          -> OWL dashboard (dashboard_action.js) + Chart.js
```
