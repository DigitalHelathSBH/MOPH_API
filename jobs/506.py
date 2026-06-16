from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from typing import Any

from common.config import get_hospital_config
from common.db import connect, fetch_dicts, insert_api_log
from common.moph_client import MophApiClient
import json

SQL_506 = """
SELECT
    main.*,
    COALESCE(NULLIF(main.icd10_list, ''), main.diagnosis_icd10) AS diagnosis_icd10_list,
    VNMST.HN,
    dbo.GetPname(VNMST.HN) AS prefix,
    main.epidem_report_group_code,
    dbo.GetNameWithoutTitle(PATIENT_NAME.FIRSTNAME) AS first_name,
    dbo.GetNameWithoutTitle(PATIENT_NAME.LASTNAME) AS last_name,
    CASE
        WHEN PATIENT_INFO.nationality IS NOT NULL THEN '0' + PATIENT_INFO.nationality
        ELSE '999'
    END AS Nation,
    PATIENT_INFO.SEX AS gender,
    REPLACE(CONVERT(varchar(10), PATIENT_INFO.BIRTHDATETIME, 111), '/', '-') AS birth_date,
    dbo.age(PATIENT_INFO.BIRTHDATETIME, main.VISITDATE) AS age_y,
    dbo.AgeMonth(PATIENT_INFO.BIRTHDATETIME, main.VISITDATE) AS age_m,
    dbo.AgeDay(PATIENT_INFO.BIRTHDATETIME, main.VISITDATE) AS age_d,
    PATIENT_INFO.MARITALSTATUS AS marital_status_id,
    PATIENT_REF.REF AS cid,
    PATIENT_ADDRESS.ADDRESS,
    ISNULL(PATIENT_ADDRESS.MOO, '') AS moo,
    PATIENT_ADDRESS.PROVINCE AS chw_code,
    PATIENT_ADDRESS.AMPHOE AS amp_code,
    PATIENT_ADDRESS.TAMBON AS tmb_code,
    PATIENT_ADDRESS.TEL AS mobile_phone,
    PATIENT_INFO.OCCUPATION,
    '1' AS epidem_person_status_id,
    'N' AS respirator_status,
    '3' AS municipal,
    'OPD' AS patient_type
FROM
(
    SELECT
        CONCAT('{', UPPER(NEWID()), '}') AS epidem_report_guid,
        ICD10_Map506.ICDGroup AS epidem_report_group_code,
        '10661' AS treated_hospital_code,
        CONVERT(varchar(19), GETDATE(), 126) AS report_datetime,
        REPLACE(CONVERT(varchar(10), VNDIAG.VISITDATE, 111), '/', '-') AS treated_date,
        REPLACE(CONVERT(varchar(10), VNDIAG.DIAGDATETIME, 111), '/', '-') AS diagnosis_date,
        dbo.GetUserFullName(VNDIAG.ENTRYBYUSERCODE) AS informer_name,
        VNDIAG.ICDCODE AS diagnosis_icd10,
        (
            SELECT dbo.Concat(VD.ICDCODE)
            FROM VNDIAG AS VD
            WHERE VD.VN = VNDIAG.VN
                AND VD.VISITDATE = VNDIAG.VISITDATE
                AND VD.SUFFIX = VNDIAG.SUFFIX
                AND VD.TYPEOFTHISDIAG <> '1'
        ) AS icd10_list,
        VNDIAG.DIAGDATETIME,
        VNDIAG.DIAGDATETIME AS specimen_date,
        VNDIAG.VN,
        VNDIAG.VISITDATE,
        VNDIAG.SUFFIX
    FROM VNDIAG
    JOIN ICD10_Map506
        ON VNDIAG.ICDCODE = ICD10_Map506.ICD10
    WHERE CONVERT(date,VNDIAG.DIAGDATETIME) = ?
        AND VNDIAG.TYPEOFTHISDIAG = '1'
) AS main
JOIN VNMST
    ON main.VN = VNMST.VN
    AND main.VISITDATE = VNMST.VISITDATE
LEFT JOIN PATIENT_NAME
    ON VNMST.HN = PATIENT_NAME.HN
    AND PATIENT_NAME.SUFFIX = 0
LEFT JOIN PATIENT_INFO
    ON VNMST.HN = PATIENT_INFO.HN
LEFT JOIN PATIENT_REF
    ON VNMST.HN = PATIENT_REF.HN
    AND PATIENT_REF.REFTYPE = '01'
LEFT JOIN PATIENT_ADDRESS
    ON VNMST.HN = PATIENT_ADDRESS.HN
    AND PATIENT_ADDRESS.SUFFIX = 1
"""


def parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today() - timedelta(days=3)


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)

def clean_int(value: Any) -> str:
    if value is None or value == "":
        return "0"
    return str(int(value))


def build_payload(row: dict[str, Any]) -> dict[str, Any]:
    hospital = get_hospital_config()
    return {
        "hospital": {
            "hospital_code": hospital.code,
            "hospital_name": hospital.name,
            "his_identifier": hospital.his_identifier,
        },
        "person": {
            "cid": clean(row.get("cid")),
            "passport_no": None,
            "prefix": clean(row.get("prefix")),
            "first_name": clean(row.get("first_name")),
            "last_name": clean(row.get("last_name")),
            "nationality": clean(row.get("Nation")),
            "gender": clean(row.get("gender")),
            "birth_date": clean(row.get("birth_date")),
            "age_y": clean_int(row.get("age_y")),
            "age_m": clean_int(row.get("age_m")),
            "age_d": clean_int(row.get("age_d")),
            "marital_status_id": clean(row.get("marital_status_id")),
            "address": clean(row.get("ADDRESS")),
            "moo": clean(row.get("moo")),
            "road": None,
            "chw_code": clean(row.get("chw_code")),
            "amp_code": clean(row.get("amp_code")),
            "tmb_code": clean(row.get("tmb_code")),
            "mobile_phone": clean(row.get("mobile_phone")),
            "occupation": clean(row.get("OCCUPATION")),
        },
        "epidem_report": {
            "epidem_report_guid": clean(row.get("epidem_report_guid")),
            "epidem_report_group_code": clean(row.get("epidem_report_group_code")),
            "treated_hospital_code": clean(row.get("treated_hospital_code")),
            "report_datetime": clean(row.get("report_datetime")),
            "onset_date": None,
            "treated_date": clean(row.get("treated_date")),
            "diagnosis_date": clean(row.get("diagnosis_date")),
            "death_date": None,
            "organism": None,
            "complication": None,
            "cdeath": None,
            "informer_name": clean(row.get("informer_name")),
            "principal_diagnosis_icd10": clean(row.get("diagnosis_icd10")),
            "diagnosis_icd10_list": clean(row.get("diagnosis_icd10_list")),
            "epidem_person_status_id": clean(row.get("epidem_person_status_id")),
            "epidem_symptom_type_id": None,
            "municipal": clean(row.get("municipal")),
            "respirator_status": clean(row.get("respirator_status")),
            "vaccinated_status": None,
            "epidem_address": None,
            "epidem_moo": None,
            "epidem_road": None,
            "epidem_chw_code": clean(row.get("chw_code")),
            "epidem_amp_code": None,
            "epidem_tmb_code": None,
            "location_gis_latitude": None,
            "location_gis_longitude": None,
            "isolate_chw_code": clean(row.get("chw_code")),
            "patient_type": clean(row.get("patient_type")),
            "active_case_finding": "ชุมชนตลาดคลองท่อม",
            "epidem_cluster_type_id": None,
            "cluster_latitude": None,
            "cluster_longitude": None,
            "comment": None,
        },
        "lab_report": {
            "specimen_date": None,
            "epidem_lab_confirm_type_id": None,
            "specimen_place_id": None,
            "lab_report_date": None,
            "lab_report_result": None,
            "lab_his_ref_code": None,
            "lab_his_ref_name": None,
            "tmlt_code": None,
        },
        "vaccination": [],
    }


def fetch_rows(target_date: date) -> list[dict[str, Any]]:
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(SQL_506, target_date.isoformat())
        return fetch_dicts(cursor)


def run(target_date: date) -> tuple[int, int, int]:
    rows = fetch_rows(target_date)
    client = MophApiClient()
    success_count = 0
    fail_count = 0

    for row in rows:
        result = client.send_506(build_payload(row))
        message_code = str(result.get("MessageCode", ""))
        if result.ok and message_code == "200":
            success_count += 1
        else:
            fail_count += 1
            print("SEND 506 FAIL", row.get("HN"), row.get("VN"), row.get("diagnosis_icd10"), result.status_code, result.text[:500])

    with connect() as conn:
        insert_api_log(conn, apiwork="506", host="moph_api/jobs/send_506.py")

    return len(rows), success_count, fail_count


def main() -> None:
    parser = argparse.ArgumentParser(description="ส่งข้อมูล API 506")
    parser.add_argument("--date", help="วันที่ DIAGDATETIME รูปแบบ YYYY-MM-DD ถ้าไม่ใส่จะใช้เมื่อวาน")
    parser.add_argument("--dry-run", action="store_true", help="ดูข้อมูล JSON ก่อนส่ง API")
    args = parser.parse_args()

    target_date = parse_date(args.date)

    if args.dry_run:
        rows = fetch_rows(target_date)

        print(f"506 วันที่ {target_date} พบข้อมูล {len(rows)} รายการ")

        for i, row in enumerate(rows, start=1):
            payload = build_payload(row)

            print("=" * 80)
            print(f"รายการที่ {i}")
            print(f"HN: {row.get('HN')} VN: {row.get('VN')} ICD: {row.get('diagnosis_icd10')}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        return

    total, success_count, fail_count = run(target_date)
    print(f"506 วันที่ {target_date} ทั้งหมด {total} สำเร็จ {success_count} ไม่สำเร็จ {fail_count}")


if __name__ == "__main__":
    main()
