from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    server: str
    database: str
    username: str
    password: str
    driver: str


@dataclass(frozen=True)
class HospitalConfig:
    code: str
    name: str
    his_identifier: str


@dataclass(frozen=True)
class MophConfig:
    token_url: str
    token_hospital_code: str
    token_user: str
    token_password_hash: str
    send_506_url: str
    send_epi_url: str
    send_dmht_url: str
    send_dt_url: str
    update_immunization_url: str
    update_lab_url: str

@dataclass(frozen=True)
class FdhConfig:
    token_url: str
    token_hospital_code: str
    token_user: str
    token_password_hash: str
    

def get_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        server=os.getenv("DB_SERVER", "10.0.1.1,1433"),
        database=os.getenv("DB_NAME", "SSBDatabase"),
        username=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        driver=os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
    )


def get_hospital_config() -> HospitalConfig:
    return HospitalConfig(
        code=os.getenv("HOSPITAL_CODE", "10661"),
        name=os.getenv("HOSPITAL_NAME", "โรงพยาบาลสระบุรี"),
        his_identifier=os.getenv("HIS_IDENTIFIER", "HIS Vendor A version 1.0"),
    )


def get_moph_config() -> MophConfig:
    return MophConfig(
        token_url=os.getenv("MOPH_TOKEN_URL", "https://cvp1.moph.go.th/token?Action=get_moph_access_token"),
        token_hospital_code=os.getenv("MOPH_TOKEN_HOSPITAL_CODE", "10661"),
        token_user=os.getenv("MOPH_TOKEN_USER", ""),
        token_password_hash=os.getenv("MOPH_TOKEN_PASSWORD_HASH", ""),
        send_506_url=os.getenv("MOPH_SEND_506_URL", "https://epidemcenter.moph.go.th/epidem506/api/Send506"),
        send_epi_url=os.getenv("MOPH_SEND_EPI_URL", "https://claim-nhso.moph.go.th/api/v1/opd/service-admissions/epi"),
        send_dmht_url=os.getenv("MOPH_SEND_DMHT_URL", "https://claim-nhso.moph.go.th/api/v1/opd/service-admissions/dmht"),
        send_dt_url=os.getenv("MOPH_SEND_DT_URL", "https://claim-nhso.moph.go.th/api/v1/opd/service-admissions/dt"),
        update_immunization_url=os.getenv("MOPH_UPDATE_IMMUNIZATION_URL", "https://cloud4.hosxp.net/api/moph/UpdateImmunization"),
        update_lab_url=os.getenv("MOPH_UPDATE_LAB_URL", "https://cvp1.moph.go.th/api/UpdateLab"),
    )

def get_fdh_config() -> FdhConfig:
    return FdhConfig(
        token_url=os.getenv("FDH_TOKEN_URL", "https://fdh.moph.go.th/token?Action=get_moph_access_token"),
        token_hospital_code=os.getenv("FDH_TOKEN_HOSPITAL_CODE", "10661"),
        token_user=os.getenv("FDH_TOKEN_USER", ""),
        token_password_hash=os.getenv("FDH_TOKEN_PASSWORD_HASH", ""),
    )