# SEC_APP production deployment (Windows + MSSQL)

The application stores relational data in Microsoft SQL Server `SEC_PORTAL`.
Uploads remain filesystem files; preserve `uploads/` and `static/uploads/` on
the production host.

## Before first run

1. Copy the project folder to the production host. Do not copy a local
   `.sec_app_session_secret` or use the SQLite file as the live database.
2. Install Python 3.12+ and create/activate the production virtual environment.
3. Run `python -m pip install -r requirements.txt`.
4. Install the browser required by the PDF-to-HTML feature:
   `python -m playwright install chromium`.
5. Install Tesseract OCR on the host if OCR features are required, and make
   its executable available on `PATH`.
6. Store the following values in the production service's secret/environment
   configuration. Never put the password in this repository. For a portable
   development deployment, the same values can instead be kept in the
   gitignored `production.env` file included beside this document.

```text
SEC_APP_DATABASE_ENGINE=mssql
SEC_APP_DB_SERVER=192.168.240.22
SEC_APP_DB_PORT=1433
SEC_APP_DB_DATABASE=SEC_PORTAL
SEC_APP_DB_UID=<runtime-account>
SEC_APP_DB_PASSWORD=<secret>
SEC_APP_SECRET_KEY=<long-random-secret>
SEC_APP_HOST=0.0.0.0
SEC_APP_PORT=5000
SEC_APP_DEBUG=false
SEC_APP_HTTPS=true
```

The runtime account needs `db_datareader` and `db_datawriter` on `SEC_PORTAL`.
It does not need `sa` or `db_ddladmin` after the schema has been migrated.

## Verify and run

From the project root in the same service environment:

```powershell
.\scripts\test_production_ready.ps1
.\scripts\start_production.ps1
```

The launcher uses Waitress, not Flask's development server. Configure the
chosen Windows service, IIS reverse proxy, or Task Scheduler job to invoke
`start_production.ps1` with the same protected environment values.
