from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from typing import Any

from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_ADMISSION = """
SELECT ADMMASTER.HN,
       (
            SELECT TOP 1
                RIGHT('00000' + CAST(VNMST.VN AS VARCHAR), 5) +
                FORMAT(VNMST.VISITDATE, 'ddMMyyyy') +
                RIGHT('00' + CAST(VNDIAG.SUFFIX AS VARCHAR), 2) AS barcode
            FROM VNMST
            JOIN VNDIAG
                ON VNMST.VN = VNDIAG.VN
               AND VNMST.VISITDATE = VNDIAG.VISITDATE
            WHERE VNMST.HN = ADMMASTER.HN
              AND VNMST.VISITDATE <= ADMMASTER.ADMDATETIME
            ORDER BY VNMST.VISITDATE DESC,
                     VNMST.VN DESC,
                     VNDIAG.SUFFIX DESC
       ) AS VN,
       ADMMASTER.AN,
       CONVERT(varchar(10), ADMMASTER.ADMDATETIME, 23) AS admit_date,
       CONVERT(varchar(8), ADMMASTER.ADMDATETIME, 108) AS admit_time,
       CONVERT(varchar(10), ADMMASTER.DISCHARGEDATETIME, 23) AS discharge_date,
       CONVERT(varchar(8), ADMMASTER.DISCHARGEDATETIME, 108) AS discharge_time,
       CASE
            WHEN ADMMASTER.DISCHARGETYPE = '1' THEN '1'
            WHEN ADMMASTER.DISCHARGETYPE = '4' THEN '3'
            WHEN ADMMASTER.DISCHARGETYPE IN ('6','7','8','9','0') THEN '9'
            ELSE NULL
       END AS discharge_type
FROM ADMMASTER
JOIN DischargeType ON ADMMASTER.DISCHARGETYPE = DischargeType.CODE
JOIN IpdDiag ON ADMMASTER.AN = IpdDiag.AN
WHERE (
        IpdDiag.icd10 IN (
            'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
            'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
        )
        OR IpdDiag.icd10 LIKE 'C%'
      )
  AND CONVERT(date, ADMMASTER.ADMDATETIME) = ?
GROUP BY ADMMASTER.HN,
         ADMMASTER.AN,
         ADMMASTER.ADMDATETIME,
         ADMMASTER.DISCHARGEDATETIME,
         ADMMASTER.DISCHARGETYPE
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
        "vn": clean(row.get("VN")),
        "an": clean(row.get("AN")),
        "admit_date": clean(row.get("admit_date")),
        "admit_time": clean(row.get("admit_time")),
        "discharge_date": clean(row.get("discharge_date")),
        "discharge_time": clean(row.get("discharge_time")),
        "discharge_type": clean(row.get("discharge_type")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_ADMISSION, target_date.isoformat())
        return fetch_dicts(cursor)


def insert_log(hn: Any, success: Any, message: Any) -> None:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'admission')
            """,
            hn,
            str(success),
            str(message),
        )
        conn.commit()


def is_success(result_ok: bool, success: Any) -> bool:
    return result_ok and str(success).lower() in ("true", "1", "y", "success")


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = [build_payload(row)]
        result = client.send_cancer_link_admission(payload)

        data = result.data if isinstance(result.data, dict) else {}
        success = data.get("success", result.ok)
        message = data.get("message", result.text)

        insert_log(row.get("HN"), success, message)

        if is_success(result.ok, success):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_ADMISSION FAIL",
                row.get("HN"),
                result.status_code,
                result.text[:500],
            )

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Admission")
    parser.add_argument("--date", help="วันที่ admit รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดู JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"CANCER_LINK_ADMISSION วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")
        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')}")
            print(json.dumps([build_payload(row)], ensure_ascii=False, indent=2))
        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_ADMISSION วันที่ {target_date} "
        f"ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()