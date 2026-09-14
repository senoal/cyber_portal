/* Central audit table for SEC_APP activity tracking. */
IF OBJECT_ID('dbo.activity_logs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.activity_logs (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        user_id INT NULL,
        username NVARCHAR(150) NULL,
        user_role NVARCHAR(50) NULL,
        event_category VARCHAR(20) NOT NULL,
        action_name VARCHAR(120) NOT NULL,
        endpoint VARCHAR(180) NULL,
        http_method VARCHAR(10) NULL,
        request_path NVARCHAR(500) NULL,
        response_status SMALLINT NULL,
        client_ip VARCHAR(64) NULL,
        duration_ms INT NULL,
        detail NVARCHAR(1000) NULL
    );
    CREATE INDEX IX_activity_logs_created_at ON dbo.activity_logs(created_at DESC);
    CREATE INDEX IX_activity_logs_user_id ON dbo.activity_logs(user_id, created_at DESC);

END;

IF OBJECT_ID('dbo.activity_log_exports', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.activity_log_exports (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        exported_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        exported_by_user_id INT NULL,
        exported_by_username NVARCHAR(150) NULL,
        range_start DATE NOT NULL,
        range_end DATE NOT NULL,
        record_count INT NOT NULL,
        archive_purged BIT NOT NULL DEFAULT 0,
        filename NVARCHAR(255) NOT NULL
    );
END;
