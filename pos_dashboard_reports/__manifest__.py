# -*- coding: utf-8 -*-
{
    "name": "POS Dashboard & Reporting Suite",
    "version": "16.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Dashboard POS ringan: grafik interaktif, 16 laporan siap export Excel/PDF, mapping kategori Tenant/Rides/Bracelet/Ticket",
    'price': 19.99,
    'currency': 'EUR',
    "description": """
POS Dashboard & Reporting Suite
================================
Modul dashboard dan reporting untuk Point of Sale (Odoo 16), dibuat khusus
untuk bisnis dengan banyak "jenis penjualan" dalam satu POS — tiket masuk,
wahana (rides), gelang (bracelet), sewa tenant, F&B, dan bundling promo —
sekaligus tetap RINGAN saat membaca data karena tidak pernah membaca
seluruh tabel transaksi.

------------------------------------------------------------------
FITUR UTAMA
------------------------------------------------------------------
* Dashboard interaktif (OWL + Chart.js): ganti laporan, rentang tanggal,
  POS, dan kasir langsung dari satu layar, tanpa reload halaman.
* Wizard filter terpisah (menu Laporan) untuk membuka laporan tertentu,
  lalu langsung Cetak PDF atau Export Excel dari popup yang sama.
* Export Excel (xlsxwriter) & PDF (QWeb) untuk seluruh 16 laporan, memakai
  query agregat yang sama dengan yang ditampilkan di layar — sehingga hasil
  export selalu konsisten dengan yang terlihat di dashboard.
* Mapping kategori produk (menu Konfigurasi > Mapping Kategori Laporan):
  admin cukup menandai kategori produk sebagai Tenant / Rides / Bracelet /
  Ticket / Bundling, dan laporan-laporan terkait langsung terisi otomatis
  tanpa perlu menambah field custom di master produk.
* Dua level akses: Dashboard User (lihat & export laporan) dan Dashboard
  Manager (tambahan: atur mapping kategori).
* PERFORMA: semua angka diambil lewat SQL agregat (GROUP BY/SUM/COUNT)
  langsung lewat cursor, bukan browse()/search() seluruh pos_order /
  pos_order_line; setiap query wajib difilter tanggal + company, dan hasil
  daftar (bukan agregat) selalu dibatasi LIMIT/OFFSET. Nama produk/
  kategori/jurnal (field translatable) baru diambil lewat ORM untuk ID
  hasil agregasi yang jumlahnya kecil, bukan per baris transaksi.

------------------------------------------------------------------
16 LAPORAN & FUNGSINYA
------------------------------------------------------------------
1.  Reporting Orders
    Daftar order POS (nomor, tanggal, POS, kasir, pelanggan, total, pajak,
    status) lengkap dengan tren jumlah order & penjualan harian.

2.  POS Payment Analysis
    Analisis penerimaan per METODE PEMBAYARAN (cash, kartu, QRIS, dsb):
    jumlah transaksi, total, rata-rata per transaksi, dan persentase (%)
    kontribusi tiap metode terhadap total penerimaan pada periode terpilih.

3.  Sales Detail
    Rincian penjualan level baris item (bukan per order): produk, qty,
    harga satuan, diskon, subtotal, dan total per transaksi.

4.  Sale Report
    Rekap penjualan per produk (semua kategori): qty terjual, subtotal,
    total, dan jumlah transaksi — untuk melihat produk terlaris.

5.  Sale per Kasir Report
    Performa tiap kasir: jumlah order yang dilayani, total penjualan,
    pajak, dan rata-rata nilai transaksi per kasir.

6.  Sale Ticket Report
    Rekap penjualan khusus kategori "Ticket" (hasil mapping kategori):
    jenis tiket apa saja yang terjual, berapa qty dan total nilainya.

7.  Sale Ticket Tax Report
    Sama seperti Sale Ticket Report, ditambah rincian DPP (subtotal),
    nilai pajak, dan nama tarif pajak yang berlaku per jenis tiket.

8.  Sale Tenant Report
    Rekap penjualan kategori "Tenant" — untuk memantau omzet tiap tenant/
    penyewa yang berjualan lewat POS yang sama.

9.  Sale Rides Report
    Rekap penjualan kategori "Rides" (wahana): wahana mana yang paling
    laku, qty tiket wahana terjual, dan total pendapatan per wahana.

10. Bracelet Report
    Rekap penjualan kategori "Bracelet" (gelang akses) — qty & total
    penjualan per jenis gelang.

11. Transaction Ticket Report
    Berbeda dari Sale Ticket Report: laporan ini level TRANSAKSI, yaitu
    daftar struk/order yang mengandung minimal satu item kategori Ticket,
    lengkap dengan jumlah item dan total per struk.

12. Summary Product Category / COA Report
    Rekap penjualan per KATEGORI PRODUK, dilengkapi akun pendapatan (Chart
    of Accounts) yang terhubung ke kategori tersebut — memudahkan rekonsiliasi
    penjualan dengan akuntansi.

13. Direksi Report (Executive Summary)
    Ringkasan eksekutif satu layar: total order, total penjualan, pajak,
    rata-rata transaksi, tren penjualan harian, kategori terlaris, top 5
    kasir, dan top 5 kategori — laporan default saat menu Dashboard dibuka.

14. Sale Order Report
    Rekap per SESI kasir (bukan per order): jam buka/tutup sesi, kasir yang
    bertugas, jumlah order, total penjualan, dan pajak selama sesi tsb.

15. Accounting Report
    Rekap total penerimaan per metode pembayaran & JURNAL akuntansi tujuan
    (mis. Kas, Bank BCA) — untuk rekonsiliasi kas/bank harian oleh finance.

16. Bundling Transaction Report
    Level transaksi (seperti Transaction Ticket Report) khusus untuk
    struk yang mengandung item kategori "Bundling" — memantau efektivitas
    paket/promo bundling.

------------------------------------------------------------------
CATATAN
------------------------------------------------------------------
* Isi dulu menu Konfigurasi > Mapping Kategori Laporan setelah instalasi
  agar laporan Tenant/Rides/Bracelet/Ticket/Bundling terisi data.
  """,
    "author": "HAJI Pentil Dev",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "account", "web"],
    "data": [
        "security/pos_dashboard_security.xml",
        "security/ir.model.access.csv",
        "wizard/pos_dashboard_wizard_views.xml",
        "views/pos_dashboard_config_views.xml",
        "views/pos_dashboard_menus.xml",
        "report/pos_dashboard_report_actions.xml",
        "report/pos_dashboard_report_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pos_dashboard_reports/static/src/css/dashboard.css",
            "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.umd.min.js",
            "pos_dashboard_reports/static/src/js/dashboard_action.js",
            "pos_dashboard_reports/static/src/xml/pos_dashboard_templates.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
