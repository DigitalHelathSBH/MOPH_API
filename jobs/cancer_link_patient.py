from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_PATIENT = SQL_CANCER_LINK_PATIENT = """
WITH fang AS
(
    SELECT ADMMASTER.HN
    FROM ADMMASTER
    JOIN IpdDiag 
        ON ADMMASTER.AN = IpdDiag.AN
    WHERE 
        (
            IpdDiag.icd10 IN 
            (
                'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
                'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
            )
            OR IpdDiag.icd10 LIKE 'C%'
        )
        AND CONVERT(date, ADMMASTER.DISCHARGEDATETIME) = ?

    GROUP BY ADMMASTER.HN

    UNION

    SELECT VNMST.HN
    FROM VNMST
    JOIN VNDIAG 
        ON VNMST.VN = VNDIAG.VN 
       AND VNMST.VISITDATE = VNDIAG.VISITDATE
    WHERE 
        (
            VNDIAG.ICDCODE IN 
            (
                'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
                'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
            )
            OR VNDIAG.ICDCODE LIKE 'C%'
        )
        AND VNMST.VISITDATE = ?

    GROUP BY VNMST.HN
)
SELECT 
    fang.HN,
    PATIENT_REF.REF,
    PATIENT_INFO.InitialNameCode,
    dbo.GetNameWithoutTitle(PATIENT_NAME.FIRSTNAME) AS firstname,
    dbo.GetSSBName(PATIENT_NAME.LASTNAME) AS lastname,
    REPLACE(CONVERT(varchar, BIRTHDATETIME, 111), '/', '-') AS birth_date,
    SEX,
    RIGHT('000' + CAST(ISNULL(NULLIF(PATIENT_INFO.NATIONALITY, ''), '999') AS varchar(3)), 3) AS NATIONALITY,
    PATIENT_ADDRESS.ADDRESS,
    ISNULL(NULLIF(CT.tamboncode, ''), '99') AS SUBDISTRICT,
    ISNULL(NULLIF(RIGHT(CT.ampurcode, 2), ''), '99') AS DISTRICT,
    ISNULL(NULLIF(CT.changwatcode, ''), '99') AS PROVINCE,
    PATIENT_ADDRESS.TEL AS PHONENUMBER
FROM fang
JOIN PATIENT_REF 
    ON fang.HN = PATIENT_REF.HN 
   AND PATIENT_REF.REFTYPE = '01'
JOIN PATIENT_INFO 
    ON fang.HN = PATIENT_INFO.HN 
   AND PATIENT_INFO.InitialNameCode IS NOT NULL
JOIN PATIENT_NAME 
    ON fang.HN = PATIENT_NAME.HN 
   AND PATIENT_NAME.SUFFIX = '0'
JOIN PATIENT_ADDRESS 
    ON fang.HN = PATIENT_ADDRESS.HN 
   AND PATIENT_ADDRESS.SUFFIX = '1'
JOIN MOPH.dbo.ctambon CT 
    ON PATIENT_ADDRESS.TAMBON = CT.ssbcode
   AND PATIENT_ADDRESS.AMPHOE = CT.ssbamp
   AND PATIENT_ADDRESS.PROVINCE = CT.ssbpro
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today() - timedelta(days=1)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "hospcode": "10661",
        "hn": clean(row.get("HN")),
        "cid": clean(row.get("REF")),
        "title": clean(row.get("InitialNameCode")),
        "firstname": clean(row.get("firstname")),
        "lastname": clean(row.get("lastname")),
        "birth_date": clean(row.get("birth_date")),
        "sex": clean(row.get("SEX")),
        "nationality": clean(row.get("NATIONALITY")),
        "address_no": clean(row.get("ADDRESS")),
        "address_moo": "",
        "subdistrict": clean(row.get("SUBDISTRICT")),
        "district": clean(row.get("DISTRICT")),
        "province": clean(row.get("PROVINCE")),
        "telephone": clean(row.get("PHONENUMBER")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_PATIENT, target_date.isoformat(), target_date.isoformat())
        return fetch_dicts(cursor)


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = [build_payload(row)]
        result = client.send_cancer_link_patient(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success")
        message = data.get("message", result.text)

        with connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO Saraburi.dbo.API_log_cancerlink
                    (HN, makedate, success, message, headersname)
                VALUES (?, GETDATE(), ?, ?, 'Patient')
                """,
                row.get("HN"),
                str(success),
                str(message),
            )
            conn.commit()

        if result.ok and str(success).lower() in ("true", "1", "y", "success"):
            success_count += 1
        else:
            fail_count += 1
            print("CANCER_LINK_PATIENT FAIL", row.get("HN"), result.status_code, result.text[:500])

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Patient")
    parser.add_argument("--date", help="วันที่ discharge/visit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"CANCER_LINK_PATIENT วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')}")
            print(json.dumps([build_payload(row)], ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(f"CANCER_LINK_PATIENT วันที่ {target_date} ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}")


if __name__ == "__main__":
    main()