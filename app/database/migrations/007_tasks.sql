/* Tasks module: SQL Server schema.  The application also creates these
   idempotently on first use, so local and production deployments stay aligned. */
IF OBJECT_ID('dbo.tasks', 'U') IS NULL
CREATE TABLE dbo.tasks (
    id INT IDENTITY(1,1) PRIMARY KEY,
    owner_id INT NOT NULL,
    title NVARCHAR(120) NOT NULL,
    description NVARCHAR(MAX) NOT NULL DEFAULT '',
    category NVARCHAR(50) NOT NULL DEFAULT 'Personal',
    due_date DATE NULL,
    priority VARCHAR(10) NOT NULL DEFAULT 'medium',
    completed BIT NOT NULL DEFAULT 0,
    canceled BIT NOT NULL DEFAULT 0,
    created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT CK_tasks_priority CHECK (priority IN ('low','medium','high'))
);

IF OBJECT_ID('dbo.task_attachments', 'U') IS NULL
CREATE TABLE dbo.task_attachments (
    id INT IDENTITY(1,1) PRIMARY KEY, task_id INT NOT NULL,
    original_name NVARCHAR(260) NOT NULL, stored_name NVARCHAR(260) NOT NULL UNIQUE,
    size BIGINT NOT NULL, uploaded_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT FK_task_attachments_task FOREIGN KEY (task_id) REFERENCES dbo.tasks(id) ON DELETE CASCADE
);

IF OBJECT_ID('dbo.task_subtasks', 'U') IS NULL
CREATE TABLE dbo.task_subtasks (
    id INT IDENTITY(1,1) PRIMARY KEY, task_id INT NOT NULL, name NVARCHAR(120) NOT NULL,
    due_date DATE NULL, notes NVARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT FK_task_subtasks_task FOREIGN KEY (task_id) REFERENCES dbo.tasks(id) ON DELETE CASCADE
);

IF OBJECT_ID('dbo.task_subtask_attachments', 'U') IS NULL
CREATE TABLE dbo.task_subtask_attachments (
    id INT IDENTITY(1,1) PRIMARY KEY, subtask_id INT NOT NULL,
    original_name NVARCHAR(260) NOT NULL, stored_name NVARCHAR(260) NOT NULL UNIQUE,
    size BIGINT NOT NULL, uploaded_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT FK_task_subtask_attachments_subtask FOREIGN KEY (subtask_id) REFERENCES dbo.task_subtasks(id) ON DELETE CASCADE
);

/* Detail views join/filter on these foreign keys.  Explicit indexes keep
   Step detail responsive as the Tasks workspace grows. */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tasks_owner_created' AND object_id = OBJECT_ID('dbo.tasks'))
    CREATE INDEX IX_tasks_owner_created ON dbo.tasks (owner_id, created_at DESC, id DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_task_attachments_task_id' AND object_id = OBJECT_ID('dbo.task_attachments'))
    CREATE INDEX IX_task_attachments_task_id ON dbo.task_attachments (task_id, id DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_task_subtasks_task_due' AND object_id = OBJECT_ID('dbo.task_subtasks'))
    CREATE INDEX IX_task_subtasks_task_due ON dbo.task_subtasks (task_id, due_date, id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_subtask_attachments_subtask_id' AND object_id = OBJECT_ID('dbo.task_subtask_attachments'))
    CREATE INDEX IX_subtask_attachments_subtask_id ON dbo.task_subtask_attachments (subtask_id, id DESC);
