/* Store a manually entered Pentest owner without requiring a users record. */
IF COL_LENGTH('dbo.pentest_tasks', 'manual_owner_name') IS NULL
BEGIN
    ALTER TABLE dbo.pentest_tasks
    ADD manual_owner_name NVARCHAR(255) NULL;
END;
