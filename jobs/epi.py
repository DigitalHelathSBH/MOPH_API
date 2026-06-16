from __future__ import annotations

import argparse
from datetime import date, datetime
from typing import Any

import pyodbc

from common.config import get_hospital_config
from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient
import json

SQL_EPI = """
SELECT
    NHSOs.dbo.GetSeqOnlyOne(VNMST.VN, VNMST.VISITDATE) AS seq,
    VNMST.HN,
    Patient_Ref.REF,
    dbo.GetTitle(VNMST.HN) AS title,
    dbo.GetNameWithoutTitle(PATIENT_NAME.FIRSTNAME) AS fname,
    dbo.GetNameWithoutTitle(PATIENT_NAME.LASTNAME) AS lname,
    Occupation.OccName,
    CASE
        WHEN MARITALSTATUS = 1 THEN '1'
        WHEN MARITALSTATUS = 2 THEN '2'
        WHEN MARITALSTATUS = 3 THEN '4'
        WHEN MARITALSTATUS = 4 THEN '1'
        WHEN MARITALSTATUS = 5 THEN '3'
        ELSE '9'
    END AS marriage,
    CONVERT(varchar, PATIENT_INFO.BIRTHDATETIME, 23) AS dob,
    CONVERT(varchar, PATIENT_INFO.SEX) AS sex,
    RIGHT(REPLICATE('0', 3) + PATIENT_INFO.nationality, 3) AS nation,
    CONVERT(varchar, VNMST.VISITDATE, 121) AS visit_date_time,
    VNMEDICINE.LOTNO,
    VNMEDICINE.QTY,
    CONVERT(varchar, EXPIRYDATE, 23) AS expiration_date,
    dbo.GetUserFullName(VNPRES.DOCTOR) AS name,
    CERTIFYPUBLICNO,
    API_Moph_Claim_EPI_Map.moph_code,
    site_code,
    route_code,
    VNMEDICINE.VN,
    VNMEDICINE.VISITDATE,
    VNMEDICINE.SUFFIX
FROM VNMEDICINE
JOIN VNMST
    ON VNMEDICINE.VISITDATE = VNMST.VISITDATE
    AND VNMEDICINE.VN = VNMST.VN
JOIN VNPRES
    ON VNMEDICINE.VISITDATE = VNPRES.VISITDATE
    AND VNMEDICINE.VN = VNPRES.VN
    AND VNMEDICINE.SUFFIX = VNPRES.SUFFIX
JOIN PATIENT_INFO
    ON VNMST.HN = PATIENT_INFO.HN
JOIN Saraburi.dbo.API_Moph_Claim_EPI_Map
    ON VNMEDICINE.STOCKCODE = API_Moph_Claim_EPI_Map.STOCKCODE
    AND DATEDIFF(MONTH, PATIENT_INFO.BIRTHDATETIME, VNMEDICINE.VISITDATE)
        BETWEEN API_Moph_Claim_EPI_Map.startmonth AND API_Moph_Claim_EPI_Map.endmonth
JOIN PATIENT_REF
    ON VNMST.HN = PATIENT_REF.HN
    AND Patient_Ref.REFTYPE = '01'
LEFT JOIN PATIENT_NAME
    ON VNMST.HN = PATIENT_NAME.HN
    AND PATIENT_NAME.SUFFIX = 0
LEFT JOIN Occupation
    ON PATIENT_INFO.OCCUPATION = Occupation.CODE
LEFT JOIN HNDOCTOR
    ON VNPRES.DOCTOR = HNDOCTOR.DOCTOR
WHERE VNMEDICINE.VISITDATE = ?
"""


SQL_DIAG = """
SELECT
    ICDCODE,
    CONVERT(varchar, DIAGDATETIME, 121) AS dx_date_time,
    CONVERT(varchar, TYPEOFTHISDIAG) AS TYPEOFTHISDIAG
FROM VNDIAG
WHERE VN = ?
    AND VISITDATE = ?
    AND SUFFIX = ?
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today()


def text16(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def fetch_epi_rows(conn: pyodbc.Connection, target_date: date) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(SQL_EPI, target_date.isoformat())
    return fetch_dicts(cursor)


def fetch_diag(conn: pyodbc.Connection, row: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(SQL_DIAG, row.get("VN"), row.get("VISITDATE"), row.get("SUFFIX"))
    rows = fetch_dicts(cursor)
    return [
        {
            "dx_date_time": text16(diag.get("dx_date_time")),
            "icd10": diag.get("ICDCODE"),
            "dx_type": diag.get("TYPEOFTHISDIAG"),
        }
        for diag in rows
    ]


def build_payload(row: dict[str, Any], diagnosis: list[dict[str, Any]]) -> dict[str, Any]:
    hospital = get_hospital_config()
    return {
        "seq": row.get("seq"),
        "hn": row.get("HN"),
        "pid": row.get("REF"),
        "id_type": "1",
        "title": row.get("title"),
        "fname": row.get("fname"),
        "lname": row.get("lname"),
        "occupa": row.get("OccName"),
        "marriage": row.get("marriage"),
        "dob": row.get("dob"),
        "sex": row.get("sex"),
        "nation": row.get("nation"),
        "hcode": hospital.code,
        "hospital_name": hospital.name,
        "visit_date_time": text16(row.get("visit_date_time")),
        "vaccine": [
            {
                "code": row.get("moph_code"),
                "lot_number": row.get("LOTNO"),
                "dose_quantity": str(row.get("QTY")),
                "manufacturer": "",
                "expiration_date": row.get("expiration_date"),
                "occurence_date_time": text16(row.get("visit_date_time")),
                "site_code": row.get("site_code"),
                "route_code": row.get("route_code"),
                "license_no": row.get("CERTIFYPUBLICNO"),
                "name": row.get("name"),
                "note": "",
            }
        ],
        "diagnosis": diagnosis,
        "prenatal": {
            "gravida": "",
            "ga_week": "",
        },
    }

def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_EPI, target_date.isoformat())
        return fetch_dicts(cursor)


def upsert_epi_response(conn: pyodbc.Connection, row: dict[str, Any], response: dict[str, Any]) -> None:
    status = str(response.get("status", ""))
    message = response.get("message_th", "")
    transaction_uid = response.get("data", {}).get("transaction_uid") if isinstance(response.get("data"), dict) else None
    seq = row.get("seq")
    hn = row.get("HN")
    cursor = conn.cursor()

    if status == "200":
        cursor.execute("SELECT COUNT(*) AS num FROM Saraburi.dbo.API_Moph_Claim_Response WHERE seq = ?", seq)
        exists = cursor.fetchone()[0] > 0
        if exists:
            cursor.execute(
                """
                UPDATE Saraburi.dbo.API_Moph_Claim_Response
                SET makedate = GETDATE(),
                    status = ?,
                    message = ?,
                    transaction_uid = ?
                WHERE seq = ?
                """,
                status,
                message,
                transaction_uid,
                seq,
            )
        else:
            cursor.execute(
                """
                INSERT INTO Saraburi.dbo.API_Moph_Claim_Response
                    (transaction_uid, HN, seq, makedate, API_Type, status, message)
                VALUES (?, ?, ?, GETDATE(), 'EPI', ?, ?)
                """,
                transaction_uid,
                hn,
                seq,
                status,
                message,
            )
    elif status == "400":
        cursor.execute(
            "SELECT COUNT(*) AS num FROM Saraburi.dbo.API_Moph_Claim_Response WHERE seq = ? AND status != '200'",
            seq,
        )
        exists = cursor.fetchone()[0] > 0
        if exists:
            cursor.execute(
                """
                UPDATE Saraburi.dbo.API_Moph_Claim_Response
                SET makedate = GETDATE(),
                    status = ?,
                    message = ?
                WHERE seq = ?
                """,
                status,
                message,
                seq,
            )
        else:
            cursor.execute(
                """
                INSERT INTO Saraburi.dbo.API_Moph_Claim_Response
                    (HN, seq, makedate, API_Type, status, message)
                VALUES (?, ?, GETDATE(), 'EPI', ?, ?)
                """,
                hn,
                seq,
                status,
                message,
            )
    conn.commit()


def run(target_date: date) -> tuple[int, int, int]:
    client = MophApiClient()
    success_count = 0
    fail_count = 0

    with connect() as conn:
        rows = fetch_epi_rows(conn, target_date)
        for row in rows:
            diagnosis = fetch_diag(conn, row)
            payload = build_payload(row, diagnosis)
            result = client.send_epi(payload)
            response_data = result.data if isinstance(result.data, dict) else {}
            status = str(response_data.get("status", ""))

            if status in ("200", "400"):
                upsert_epi_response(conn, row, response_data)

            if status == "200":
                success_count += 1
            else:
                fail_count += 1
                print("SEND EPI FAIL", row.get("HN"), row.get("seq"), result.status_code, result.text[:500])

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล API EPI")
    parser.add_argument("--date", help="วันที่ VNMEDICINE.VISITDATE รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้วันนี้")
    parser.add_argument("--dry-run", action="store_true", help="ดูข้อมูล JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)

    if args.dry_run:
        with connect() as conn:
            rows = fetch_epi_rows(conn, target_date)

            print(f"EPI วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")

            for i, row in enumerate(rows, start=1):
                diagnosis = fetch_diag(conn, row)
                payload = build_payload(row, diagnosis)

                print("=" * 80)
                print(f"รายการที่ {i}")
                print(f"HN: {row.get('HN')} SEQ: {row.get('seq')} VN: {row.get('VN')}")
                print(json.dumps(payload, ensure_ascii=False, indent=2))

        return

    total, success_count, fail_count = run(target_date)
    print(f"EPI วันที่ {target_date} ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}")


if __name__ == "__main__":
    main()
