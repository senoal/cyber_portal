/* Modern Werkzeug password hashes require more space than legacy columns. */
DECLARE @username_length INT = (
    SELECT CHARACTER_MAXIMUM_LENGTH
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'username'
);
DECLARE @password_length INT = (
    SELECT CHARACTER_MAXIMUM_LENGTH
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'password'
);

IF @username_length IS NOT NULL AND @username_length < 150
    ALTER TABLE dbo.users ALTER COLUMN username NVARCHAR(150) NOT NULL;

IF @password_length IS NOT NULL AND @password_length < 255
    ALTER TABLE dbo.users ALTER COLUMN password NVARCHAR(255) NOT NULL;
