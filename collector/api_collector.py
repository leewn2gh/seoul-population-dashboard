"""
수집기 공통 부모 클래스 (담당: 이준호)

서울시 OpenAPI 호출 → 응답 해석 → 날짜별 CSV 저장 순서는 모든 수집기가 같다.
그 순서와 재시도·저장은 ApiCollector가 맡고, 응답 해석(parse)만 자식 클래스가 구현한다.

    ApiCollector «abstract»
      ├─ PopulationCollector   (collector/collect.py)       실시간 인구데이터
      └─ CityDataCollector     (collector/collect_city.py)  실시간 도시데이터 요약

새 API를 붙일 때는 ApiCollector를 상속한 클래스 하나만 만들면 된다.
"""
import os
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
PLACES_FILE = ROOT / "data" / "places.xlsx"
KST = timezone(timedelta(hours=9))
FALLBACK_CODES = [f"POI{n:03d}" for n in range(1, 131)]


class ApiError(Exception):
    """인증키 오류, 없는 장소처럼 다시 시도해도 결과가 같은 오류"""


def load_place_codes() -> List[str]:
    """수집할 장소 코드 목록 (data/places.xlsx, 없으면 POI001~POI130)"""
    if not PLACES_FILE.exists():
        print(f"[안내] {PLACES_FILE.name} 이 없어 POI001~POI130 을 시도합니다.")
        return FALLBACK_CODES
    df = pd.read_excel(PLACES_FILE)
    code_col = next((c for c in df.columns if "CD" in str(c).upper() or "코드" in str(c)), None)
    if code_col is None:
        raise SystemExit(f"{PLACES_FILE.name} 에서 장소 코드 열을 찾지 못했습니다. 열 이름: {list(df.columns)}")
    return df[code_col].dropna().astype(str).str.strip().tolist()


def api_error_message(data: dict) -> str:
    """서울시 API 오류 응답의 코드·메시지"""
    result = data.get("RESULT", {}) if isinstance(data, dict) else {}
    code = result.get("RESULT.CODE") or result.get("CODE")
    msg = result.get("RESULT.MESSAGE") or result.get("MESSAGE")
    return f"{code} {msg}"


class ApiCollector(ABC):
    """서울시 OpenAPI 수집기의 공통 부모. 자식은 아래 클래스 속성과 parse()만 정하면 된다."""

    NAME: str = ""                    # 로그에 붙는 이름 ("" 이면 생략)
    KEY_ENV: str = ""                 # 인증키 환경변수 이름
    OUT_ENV: str = ""                 # 저장 폴더 환경변수 이름
    DEFAULT_OUT: Path = ROOT / "data" / "raw"
    SERVICE: str = ""                 # API 서비스 이름 (citydata_ppltn, citydata 등)
    TIMEOUT: int = 20                 # 요청 1번의 제한 시간(초)
    RETRY_WAIT: int = 2               # 재시도 대기 (2, 4, 6초 ...)
    DEDUP: Tuple[str, ...] = ("AREA_CD", "COLLECTED_AT")   # 같은 파일 안에서 중복으로 보는 열
    COLUMNS: Optional[List[str]] = None                    # 저장할 열 순서 (None이면 받은 그대로)
    BASE_URL = "http://openapi.seoul.go.kr:8088/{key}/json/{service}/1/5/{area}"

    def __init__(self, api_key: str, out_dir: Path, codes: Optional[List[str]] = None,
                 retries: int = 3, workers: int = 6):
        self.__api_key = api_key      # 키는 바깥에서 읽지 못하게 숨김
        self.out_dir = Path(out_dir)
        self.codes = codes
        self.retries = retries
        self.workers = workers

    @classmethod
    def from_env(cls) -> Optional["ApiCollector"]:
        """환경변수(인증키, 저장 폴더)로 수집기를 만든다. 키가 없으면 None"""
        key = os.environ.get(cls.KEY_ENV, "").strip()
        if not key:
            print(f"{cls.KEY_ENV} 가 설정되지 않았습니다.")
            return None
        return cls(key, Path(os.environ.get(cls.OUT_ENV, cls.DEFAULT_OUT)))

    # ── 자식이 구현 ─────────────────────────────────────
    @abstractmethod
    def parse(self, data: dict) -> dict:
        """API 응답(JSON) → 저장할 한 줄(dict). 장소 기록이 없으면 ApiError"""

    def after_collect(self, rows: List[dict]) -> None:
        """수집이 끝난 뒤 추가로 할 일 (기본은 없음)"""

    def check_file(self, path: Path) -> None:
        """저장한 파일 점검 (기본은 없음)"""

    # ── 공통 처리 ───────────────────────────────────────
    def url(self, code: str) -> str:
        return self.BASE_URL.format(key=self.__api_key, service=self.SERVICE, area=code)

    def fetch(self, code: str) -> dict:
        """장소 1곳 호출 → parse() 결과. 네트워크 오류는 재시도, ApiError는 바로 실패"""
        last_error = None
        for attempt in range(self.retries):
            try:
                resp = requests.get(self.url(code), timeout=self.TIMEOUT)
                resp.raise_for_status()
                return self.parse(resp.json())
            except ApiError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(self.RETRY_WAIT * (attempt + 1))
        raise ApiError(f"요청 실패: {last_error}")

    def save(self, rows: List[dict]) -> Path:
        """한국 시간 날짜별 CSV에 추가 (DEDUP 기준으로 중복 제거)"""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{datetime.now(KST):%Y-%m-%d}.csv"
        new = pd.DataFrame(rows, columns=self.COLUMNS) if self.COLUMNS else pd.DataFrame(rows)
        if path.exists():
            new = pd.concat([pd.read_csv(path, dtype=str), new.astype(str)], ignore_index=True)
        new = new.drop_duplicates(subset=list(self.DEDUP), keep="first")
        new.to_csv(path, index=False, encoding="utf-8-sig")
        self.check_file(path)
        return path

    def run(self) -> int:
        """전체 장소 수집 → 저장. 종료코드(0 성공, 1 실패)를 돌려준다"""
        codes = self.codes or load_place_codes()
        collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

        def task(code):
            try:
                row = self.fetch(code)
                row["COLLECTED_AT"] = collected_at
                return code, row, None
            except Exception as e:
                return code, None, str(e)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(task, codes))

        rows = [row for _, row, _ in results if row]
        errors = [(code, err) for code, _, err in results if err]
        prefix = f"{self.NAME} " if self.NAME else ""
        print(f"{prefix}수집 {len(rows)}곳 / 실패 {len(errors)}곳 ({collected_at})")
        for code, err in errors[:10]:
            print(f"  - {code}: {err}")
        if not rows:
            print("한 곳도 수집하지 못했습니다. 인증키와 호출 한도를 확인하세요.")
            return 1

        self.after_collect(rows)
        print(f"저장: {self.save(rows)}")
        return 0
