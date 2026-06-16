from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from common.config import get_hospital_config
from common.db import connect, fetch_dicts
from common.moph_client import MophApiClient


SQL_CANCER_LINK_SERVICE = """
SELECT
    HN,
    RIGHT('00000' + VNMST.VN, 5)
        + FORMAT(VNMST.VISITDATE, 'ddMMyyyy')
        + RIGHT('00' + CAST(VNDIAG.SUFFIX AS varchar), 2) AS barcode,
    VNMST.VN,
    CONVERT(varchar(10), VNMST.VISITDATE, 23) AS vstdate,
    CONVERT(varchar(8), VNMST.VISITINDATETIME, 108) AS vsttime,
    CASE
        WHEN VNPRES.DoctorMemo IS NOT NULL THEN dbo.RTF2Html(VNPRES.DoctorMemo)
    END AS cc,
    VNPRES.PresentIllness AS hpi,
    RightCodeView.CancerRightCode AS pttype,
    CONVERT(decimal(10, 2), TEMPERATURE) AS btemp,
    BPHIGH AS sbp,
    BPLOW AS dbp,
    PULSERATE AS pr,
    RESPIRERATE AS rr,
    CONVERT(decimal(10, 2), BODYWEIGHT) AS weight,
    CONVERT(decimal(10, 2), HEIGHT) AS height
FROM SSBDatabase.dbo.VNMST
JOIN VNPRES
    ON VNMST.VN = VNPRES.VN
   AND VNMST.VISITDATE = VNPRES.VISITDATE
JOIN VNDIAG
    ON VNMST.VN = VNDIAG.VN
   AND VNMST.VISITDATE = VNDIAG.VISITDATE
   AND VNPRES.SUFFIX = VNDIAG.SUFFIX
JOIN RightCodeView
    ON VNPRES.RIGHTCODE = RightCodeView.RightCode
WHERE
    (
        VNDIAG.ICDCODE IN
        (
            'Z014', 'Z124', 'R87', 'N87', 'D06', 'Z121',
            'K635', 'K573', 'K51', 'Z123', 'Z016', 'N63'
        )
        OR VNDIAG.ICDCODE LIKE 'C%'
    )
    AND CONVERT(date, VNMST.VISITDATE) = ?
GROUP BY
    HN,
    VNMST.VN,
    VNMST.VISITDATE,
    VNMST.VISITINDATETIME,
    VNPRES.PresentIllness,
    VNPRES.DoctorMemo,
    RightCodeView.CancerRightCode,
    TEMPERATURE,
    BPHIGH,
    BPLOW,
    PULSERATE,
    RESPIRERATE,
    BODYWEIGHT,
    HEIGHT,
    VNDIAG.SUFFIX
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()

    return date.today() - timedelta(days=1)


def clean(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, Decimal):
        return format(value, "f")

    return str(value).strip()


def strip_html(value: Any) -> str:
    return re.sub(r"<[^>]*>", "", clean(value)).strip()


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    hospital = get_hospital_config()

    return {
        "hospcode": hospital.code,
        "hn": clean(row.get("HN")),
        "vn": clean(row.get("barcode")),
        "vstdate": clean(row.get("vstdate")),
        "vsttime": clean(row.get("vsttime")),
        "cc": strip_html(row.get("cc")),
        "hpi": clean(row.get("hpi")),
        "pttype": clean(row.get("pttype")),
        "btemp": clean(row.get("btemp")),
        "sbp": clean(row.get("sbp")),
        "dbp": clean(row.get("dbp")),
        "pr": clean(row.get("pr")),
        "rr": clean(row.get("rr")),
        "weight": clean(row.get("weight")),
        "height": clean(row.get("height")),
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_CANCER_LINK_SERVICE, target_date.isoformat())
        return fetch_dicts(cursor)


def insert_cancer_link_log(
    row: dict[str, Any],
    response_data: dict[str, Any],
    fallback_text: str,
) -> None:
    success = response_data.get("success", "")
    message = response_data.get("message", fallback_text)

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Saraburi.dbo.API_log_cancerlink
                (HN, makedate, success, message, headersname)
            VALUES (?, GETDATE(), ?, ?, 'service')
            """,
            row.get("HN"),
            str(success),
            str(message),
        )
        conn.commit()


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()

    success_count = 0
    fail_count = 0

    for row in rows:
        payload = [build_payload(row)]
        result = client.send_cancer_link_service(payload)

        response_data = result.data if isinstance(result.data, dict) else {}
        insert_cancer_link_log(row, response_data, result.text)

        success = str(response_data.get("success", "")).lower()

        if result.ok and success in ("true", "1", "y", "yes", "success"):
            success_count += 1
        else:
            fail_count += 1
            print(
                "CANCER_LINK_SERVICE FAIL",
                row.get("HN"),
                result.status_code,
                result.text[:500],
            )

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล Cancer Link Service")
    parser.add_argument(
        "--date",
        help="วันที่ VISITDATE รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ดู JSON ก่อนส่ง API",
    )

    args = parser.parse_args()
    target_date = parse_date(args.date)
    rows = fetch_rows(target_date)

    if args.dry_run:
        print(f"CANCER_LINK_SERVICE วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")

        for i, row in enumerate(rows, start=1):
            print("=" * 80)
            print(f"รายการที่ {i} HN: {row.get('HN')} VN: {row.get('VN')}")
            print(json.dumps([build_payload(row)], ensure_ascii=False, indent=2))

        return

    total, success_count, fail_count = run(target_date)
    print(
        f"CANCER_LINK_SERVICE วันที่ {target_date} "
        f"ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}"
    )


if __name__ == "__main__":
    main()