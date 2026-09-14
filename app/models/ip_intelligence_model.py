from app.database.db import get_connection
import pandas as pd


def get_all_ip(page=1, per_page=10):

    offset = (page - 1) * per_page

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
    """)

    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT
            id,
            blacklisted_address,
            description,
            status
        FROM ip_intelligence
        ORDER BY id DESC
        OFFSET {offset} ROWS
        FETCH NEXT {per_page} ROWS ONLY
    """)

    columns = [col[0] for col in cursor.description]

    data = [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

    conn.close()

    return data, total

def insert_ip(
        blacklisted_address,
        description,
        status):

    print(
        f"INSERTING => "
        f"{blacklisted_address} | "
        f"{status}"
    )

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ip_intelligence
        (
            blacklisted_address,
            description,
            status
        )
        VALUES (?, ?, ?)
    """,
    (
        blacklisted_address,
        description,
        status
    ))

    conn.commit()

    conn.close()
    
    
def get_ip_summary():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
    """)

    total_ip = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE status = 'Block'
    """)

    total_block = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE status = 'Monitor'
    """)

    total_monitor = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE status IN ('Allow', 'Whitelist')
    """)

    total_allow = cursor.fetchone()[0]

    conn.close()

    return {
        "total_ip": total_ip,
        "total_block": total_block,
        "total_monitor": total_monitor,
        "total_allow": total_allow
    }
    
def ip_exists(ip):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE blacklisted_address = ?
    """,
    (ip,))

    total = cursor.fetchone()[0]

    conn.close()

    return total > 0

def search_ip(
        keyword,
        page=1,
        per_page=10):

    offset = (page - 1) * per_page

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE blacklisted_address LIKE ?
    """,
    (f"%{keyword}%",))

    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            id,
            blacklisted_address,
            description,
            status
        FROM ip_intelligence
        WHERE blacklisted_address LIKE ?
        ORDER BY id DESC
        OFFSET ? ROWS
        FETCH NEXT ? ROWS ONLY
    """,
    (
        f"%{keyword}%",
        offset,
        per_page
    ))

    columns = [
        col[0]
        for col in cursor.description
    ]

    data = [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

    conn.close()

    return data, total


def get_ip_by_id(ip_id):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            blacklisted_address,
            description,
            status
        FROM ip_intelligence
        WHERE id = ?
    """,
    (ip_id,))

    row = cursor.fetchone()

    if not row:

        conn.close()
        return None

    data = {
        "id": row[0],
        "blacklisted_address": row[1],
        "description": row[2],
        "status": row[3]
    }

    conn.close()

    return data


def update_ip(
        ip_id,
        blacklisted_address,
        description,
        status):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        UPDATE ip_intelligence
        SET
            blacklisted_address = ?,
            description = ?,
            status = ?
        WHERE id = ?
    """,
    (
        blacklisted_address,
        description,
        status,
        ip_id
    ))

    conn.commit()

    conn.close()
    
def get_ip_summary():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
    """)
    total_ip = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE status = 'Block'
    """)
    total_block = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM ip_intelligence
        WHERE status = 'Allow'
    """)
    total_allow = cursor.fetchone()[0]

    conn.close()

    return {
        "total_ip": total_ip,
        "total_block": total_block,
        "total_allow": total_allow
    }