# Migrasi MSSQL ke SQLite

SEC_APP menggunakan SQLite sebagai satu-satunya database runtime. Tidak ada
alamat server atau kredensial MSSQL pada konfigurasi aplikasi.

## Membuat snapshot lokal

1. Buat akun SQL Server khusus `read-only` untuk database `SEC_PORTAL`.
2. Di PowerShell, isi variabel hanya untuk sesi migrasi:

```powershell
$env:SEC_APP_DB_SERVER = "server-production"
$env:SEC_APP_DB_DATABASE = "SEC_PORTAL"
$env:SEC_APP_DB_UID = "sec_app_exporter"
$env:SEC_APP_DB_PASSWORD = "<password akun read-only>"
python scripts/migrate_mssql_to_sqlite.py instance/sec_app.sqlite3
```

Skrip menolak target yang sudah ada, membaca metadata serta data dari MSSQL,
mempertahankan primary key, membuat foreign key SQLite, dan membatalkan target
jika jumlah baris atau integritas relasi tidak sesuai. Ia tidak menjalankan
INSERT, UPDATE, DELETE, atau DDL terhadap MSSQL.

## Menjalankan lokal

```powershell
$env:SEC_APP_SQLITE_PATH = "instance/sec_app.sqlite3"
python run.py
```

Jangan meng-commit file `.sqlite3`; aturan `.gitignore` telah tersedia.

## Rollback

SQLite hanya berada di `instance/sec_app.sqlite3`. Tutup aplikasi lalu ganti
file tersebut dengan salinan snapshot sebelumnya. Database MSSQL production
tidak disentuh oleh proses ini.

## Catatan deployment

Salin file SQLite hasil snapshot beserta folder upload yang diperlukan ke
server. Jalankan aplikasi dengan path SQLite absolut dan batasi izin file ini
hanya kepada akun Windows yang menjalankan aplikasi.
