/* Run once on SQL Server to persist menu access configured by an administrator. */
IF OBJECT_ID('dbo.user_menu_access', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_menu_access (
        user_id INT NOT NULL,
        menu_key VARCHAR(50) NOT NULL,
        CONSTRAINT PK_user_menu_access PRIMARY KEY (user_id, menu_key),
        CONSTRAINT FK_user_menu_access_users FOREIGN KEY (user_id)
            REFERENCES dbo.users(id) ON DELETE CASCADE
    );
END;
