from app.database.db import get_connection


# =====================================================
# INSERT BULK DATA VA
# =====================================================
def insert_va_bulk(records):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        for row in records:

            cursor.execute("""
                INSERT INTO VA_Assessment
                (
                    Scan_Date,
                    Source,
                    Asset,
                    Asset_Type,
                    Critical,
                    High,
                    Medium,
                    Low,
                    Info,
                    Risk_Level
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["scan_date"],
                row["source"],
                row["asset"],
                row["asset_type"],
                int(row["critical"]),
                int(row["high"]),
                int(row["medium"]),
                int(row["low"]),
                int(row["info"]),
                row["risk_level"]
            ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()


# =====================================================
# GET 5 DATA TERBARU
# =====================================================
def get_latest_imported(limit=5):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT TOP {limit}
            VA_ID,
            Scan_Date,
            Source,
            Asset,
            Asset_Type,
            Critical,
            High,
            Medium,
            Low,
            Info,
            Total_Vulnerability,
            Risk_Level,
            Created_At
        FROM VA_Assessment
        ORDER BY Created_At DESC
    """)

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({

            "va_id": row.VA_ID,

            "source": row.Source,

            "scan_date": row.Scan_Date,

            "asset": row.Asset,

            "asset_type": row.Asset_Type,

            "critical": row.Critical,

            "high": row.High,

            "medium": row.Medium,

            "low": row.Low,

            "info": row.Info,

            "total": row.Total_Vulnerability,

            "risk_level": row.Risk_Level,

            "created_at": row.Created_At

        })

    conn.close()

    return result


# =====================================================
# TOTAL DATA VA
# =====================================================
def get_total_va():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS Total
        FROM VA_Assessment
    """)

    row = cursor.fetchone()

    conn.close()

    return row.Total if row else 0


# =====================================================
# VA COVERAGE TRACKER
# =====================================================
def get_va_tracker_data():
    """Return the registered asset/month pairs used by the VA coverage tracker."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                LTRIM(RTRIM(Asset)) AS Asset,
                YEAR(Scan_Date) AS Scan_Year,
                MONTH(Scan_Date) AS Scan_Month,
                COUNT(*) AS Scan_Count,
                MAX(Scan_Date) AS Latest_Scan_Date
            FROM VA_Assessment
            WHERE Asset IS NOT NULL
              AND LTRIM(RTRIM(Asset)) <> ''
              AND Scan_Date IS NOT NULL
            GROUP BY
                LTRIM(RTRIM(Asset)),
                YEAR(Scan_Date),
                MONTH(Scan_Date)
            ORDER BY Asset, Scan_Year DESC, Scan_Month ASC
        """)

        return [
            {
                "asset": row.Asset,
                "year": row.Scan_Year,
                "month": row.Scan_Month,
                "scan_count": row.Scan_Count,
                "latest_scan_date": row.Latest_Scan_Date,
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


# =====================================================
# TOTAL VULNERABILITY
# =====================================================
def get_total_vulnerability():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ISNULL(SUM(Total_Vulnerability),0)
        FROM VA_Assessment
    """)

    total = cursor.fetchone()[0]

    conn.close()

    return total


# =====================================================
# TOP RISK ASSET
# =====================================================
def get_top_risk_asset():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT TOP 1
            Asset,
            Total_Vulnerability
        FROM VA_Assessment
        ORDER BY Total_Vulnerability DESC
    """)

    row = cursor.fetchone()

    conn.close()

    if row:

        return {
            "asset": row.Asset,
            "total": row.Total_Vulnerability
        }

    return None

# =====================================================
# CREATE SINGLE VA RECORD
# =====================================================
def create_va_record(data):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO VA_Assessment
            (
                Scan_Date,
                Source,
                Asset,
                Asset_Type,
                Critical,
                High,
                Medium,
                Low,
                Info,
                Risk_Level
            )
            OUTPUT INSERTED.VA_ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["scan_date"],
            data["source"],
            data["asset"],
            data["asset_type"],
            int(data["critical"]),
            int(data["high"]),
            int(data["medium"]),
            int(data["low"]),
            int(data["info"]),
            data["risk_level"]
        ))

        va_id = cursor.fetchone()[0]

        conn.commit()

        return va_id

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()
        
# =====================================================
# SEARCH & FILTER VA
# =====================================================
def search_va(
    keyword="",
    risk_level="",
    date_from="",
    date_to="",
    page=None,
    per_page=None,
):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            VA_ID,
            Scan_Date,
            Asset,
            Source,
            Asset_Type,
            Critical,
            High,
            Medium,
            Low,
            Info,
            Total_Vulnerability,
            Risk_Level,
            Created_At
        FROM VA_Assessment
        WHERE 1=1
    """

    params = []

    # Search Asset / Asset Type
    if keyword:
        query += """
            AND (
                Asset LIKE ?
                OR Asset_Type LIKE ?
                OR Source LIKE ?
            )
        """
        params.extend([
            f"%{keyword}%",
            f"%{keyword}%",
            f"%{keyword}%"
        ])

    # Risk Level
    if risk_level:
        query += """
            AND Risk_Level = ?
        """
        params.append(risk_level)

    # Date From
    if date_from:
        query += """
            AND Scan_Date >= ?
        """
        params.append(date_from)

    # Date To
    if date_to:
        query += """
            AND Scan_Date <= ?
        """
        params.append(date_to)

    query += """
        ORDER BY Scan_Date DESC
    """

    if page is not None and per_page is not None:
        query += " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY "
        params.extend([(max(1, page) - 1) * per_page, per_page])

    cursor.execute(query, params)

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({

            "va_id": row.VA_ID,
            "scan_date": row.Scan_Date,
            "asset": row.Asset,
            "scan_date": row.Scan_Date,
            "source": row.Source,
            "asset_type": row.Asset_Type,
            "critical": row.Critical,
            "high": row.High,
            "medium": row.Medium,
            "low": row.Low,
            "info": row.Info,
            "total": row.Total_Vulnerability,
            "risk_level": row.Risk_Level,
            "created_at": row.Created_At

        })

    conn.close()

    return result

# =====================================================
# GET VA BY ID
# =====================================================
def get_va_by_id(va_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            VA_ID,
            Scan_Date,
            Source,
            Asset,
            Asset_Type,
            Critical,
            High,
            Medium,
            Low,
            Info,
            Total_Vulnerability,
            Risk_Level,
            Created_At,
            Updated_At
        FROM VA_Assessment
        WHERE VA_ID = ?
    """, (va_id,))

    row = cursor.fetchone()

    conn.close()

    return row

# =====================================================
# UPDATE VA
# =====================================================
def update_va_record(va_id, data):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            UPDATE VA_Assessment
            SET
                Scan_Date = ?,
                Asset = ?,
                Source = ?,
                Asset_Type = ?,
                Critical = ?,
                High = ?,
                Medium = ?,
                Low = ?,
                Info = ?,
                Risk_Level = ?
            WHERE VA_ID = ?
        """,
        (
            data["scan_date"],
            data["asset"],
            data["source"],
            data["asset_type"],
            int(data["critical"]),
            int(data["high"]),
            int(data["medium"]),
            int(data["low"]),
            int(data["info"]),
            data["risk_level"],
            va_id
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()
        
# =====================================================
# DELETE VA
# =====================================================
def delete_va_record(va_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            DELETE
            FROM VA_Assessment
            WHERE VA_ID = ?
        """, (va_id,))

        conn.commit()

        return True

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()
        
        
# =====================================================
# DASHBOARD SUMMARY
# =====================================================
def get_dashboard_summary(
        date_from=None,
        date_to=None,
        asset_type=None,
        risk_level=None):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            COUNT(DISTINCT NULLIF(LTRIM(RTRIM(Asset)), '')) AS TotalAsset,
            ISNULL(SUM(Total_Vulnerability),0) AS TotalVulnerability,
            ISNULL(SUM(Critical),0) AS TotalCritical,
            ISNULL(SUM(High),0) AS TotalHigh,
            ISNULL(SUM(Medium),0) AS TotalMedium,
            ISNULL(SUM(Low),0) AS TotalLow
        FROM VA_Assessment
        WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ? "
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ? "
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ? "
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ? "
        params.append(risk_level)

    cursor.execute(query, params)

    row = cursor.fetchone()

    conn.close()

    return {
        "total_asset": row.TotalAsset or 0,
        "total_vulnerability": row.TotalVulnerability or 0,
        "critical": row.TotalCritical or 0,
        "high": row.TotalHigh or 0,
        "medium": row.TotalMedium or 0,
        "low": row.TotalLow or 0
    }
    
    
# =====================================================
# RISK DISTRIBUTION
# =====================================================
def get_risk_distribution(
        date_from=None,
        date_to=None,
        asset_type=None,
        risk_level=None):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            Risk_Level,
            COUNT(*) AS Total
        FROM VA_Assessment
        WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ? "
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ? "
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ? "
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ? "
        params.append(risk_level)

    query += """
        GROUP BY Risk_Level
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()

    result = {
        "High": 0,
        "Medium": 0,
        "Low": 0
    }

    for row in rows:
        result[row.Risk_Level] = row.Total

    total = (
        result["High"] +
        result["Medium"] +
        result["Low"]
    )

    if total > 0:

        result["High_Pct"] = round(
            result["High"] * 100 / total
        )

        result["Medium_Pct"] = round(
            result["Medium"] * 100 / total
        )

        result["Low_Pct"] = round(
            result["Low"] * 100 / total
        )

    else:

        result["High_Pct"] = 0
        result["Medium_Pct"] = 0
        result["Low_Pct"] = 0

    result["Total"] = total

    conn.close()

    return result


# =====================================================
# VULNERABILITY TREND
# =====================================================
def get_vulnerability_trend(
        date_from=None,
        date_to=None,
        asset_type=None,
        risk_level=None):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            Scan_Date,
            SUM(Total_Vulnerability) AS Total
        FROM VA_Assessment
        WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ? "
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ? "
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ? "
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ? "
        params.append(risk_level)

    query += """
        GROUP BY Scan_Date
        ORDER BY Scan_Date
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({
            "scan_date": str(row.Scan_Date),
            "total": row.Total
        })

    conn.close()

    return result

def get_vulnerability_by_asset_type(
    date_from=None,
    date_to=None,
    asset_type=None,
    risk_level=None
):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            Asset_Type,
            SUM(Total_Vulnerability) AS Total
        FROM VA_Assessment
        WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ?"
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ?"
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ?"
        params.append(risk_level)

    query += """
        GROUP BY Asset_Type
        ORDER BY Total DESC
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()

    conn.close()

    return [
        {
            "asset_type": row.Asset_Type,
            "total": row.Total
        }
        for row in rows
    ]
    
def get_top5_asset_risk_score(
    date_from=None,
    date_to=None,
    asset_type=None,
    risk_level=None
):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT TOP 5

            Asset,
            Source,

            MAX(Risk_Level) AS Risk_Level,

            SUM(
                (Critical * 10) +
                (High * 7) +
                (Medium * 4) +
                (Low * 2) +
                (Info * 1)
            ) AS Risk_Score

        FROM VA_Assessment

        WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ?"
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ?"
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ?"
        params.append(risk_level)

    query += """
    GROUP BY
        Asset,
        Source

    ORDER BY
        Risk_Score DESC
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({

            "asset": row.Asset,
            "source": row.Source,
            "risk_score": row.Risk_Score,
            "risk_level": row.Risk_Level

        })

    conn.close()

    return result

def get_top5_critical_vulnerability(
    date_from=None,
    date_to=None,
    asset_type=None,
    risk_level=None
):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT TOP 5

            Asset,
            Critical,
            High,
            Risk_Level

        FROM VA_Assessment

        WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ?"
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ?"
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ?"
        params.append(risk_level)

    query += """
        ORDER BY Critical DESC,
                 High DESC
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({

            "asset": row.Asset,
            "critical": row.Critical,
            "high": row.High,
            "risk_level": row.Risk_Level

        })

    conn.close()

    return result


def get_vulnerability_severity_by_asset(
    date_from=None,
    date_to=None,
    asset_type=None,
    risk_level=None
):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT TOP 5

        Asset,

        SUM(Critical) AS Critical,
        SUM(High)     AS High,
        SUM(Medium)   AS Medium,
        SUM(Low)      AS Low,
        SUM(Info)     AS Info

    FROM VA_Assessment

    WHERE 1=1
    """

    params = []

    if date_from:
        query += " AND Scan_Date >= ? "
        params.append(date_from)

    if date_to:
        query += " AND Scan_Date <= ? "
        params.append(date_to)

    if asset_type:
        query += " AND Asset_Type = ? "
        params.append(asset_type)

    if risk_level:
        query += " AND Risk_Level = ? "
        params.append(risk_level)

    query += """
    GROUP BY Asset
    ORDER BY
        SUM(Critical) DESC,
        SUM(High) DESC
    """

    cursor.execute(query, params)

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({

            "asset": row.Asset,

            "critical": row.Critical,
            "high": row.High,
            "medium": row.Medium,
            "low": row.Low,
            "info": row.Info

        })

    conn.close()

    return result


def save_va_attachment(data):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO VA_Attachment
            (
                VA_ID,
                File_Name,
                File_Original_Name,
                File_Path,
                File_Type,
                File_Size,
                Uploaded_By
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["va_id"],
            data["file_name"],
            data["original_name"],
            data["file_path"],
            data["file_type"],
            data["file_size"],
            data["uploaded_by"]
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()
        
def get_attachment_by_va(va_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT TOP 1
            Attachment_ID,
            VA_ID,
            File_Name,
            File_Original_Name,
            File_Path,
            File_Type,
            File_Size,
            Uploaded_By,
            Uploaded_At
        FROM VA_Attachment
        WHERE VA_ID = ?
        ORDER BY Uploaded_At DESC, Attachment_ID DESC
    """, (va_id,))

    row = cursor.fetchone()

    conn.close()

    return row

def delete_attachment(attachment_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            DELETE
            FROM VA_Attachment
            WHERE Attachment_ID = ?
        """, (attachment_id,))

        conn.commit()

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()
        
def delete_attachment_by_va(va_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            DELETE
            FROM VA_Attachment
            WHERE VA_ID = ?
        """, (va_id,))

        conn.commit()

    except Exception as e:

        conn.rollback()
        raise e

    finally:

        conn.close()
        
        
# =====================================================
# GET ATTACHMENT BY ID
# =====================================================
def get_attachment_by_id(attachment_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            Attachment_ID,
            VA_ID,
            File_Name,
            File_Original_Name,
            File_Path,
            File_Type,
            File_Size,
            Uploaded_By,
            Uploaded_At
        FROM VA_Attachment
        WHERE Attachment_ID = ?
    """, (attachment_id,))

    row = cursor.fetchone()

    conn.close()

    return row
