"""
서울시 실시간 인구데이터 수집기 (담당: 이준호)

GitHub Actions가 1시간마다 실행한다. 장소마다 API를 한 번씩 호출해서
data/raw/YYYY-MM-DD.csv (한국 시간 기준 날짜별 파일) 에 한 줄씩 추가한다.

직접 실행:  SEOUL_API_KEY=발급받은키 python collector/collect.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_collector import ROOT, ApiCollector, ApiError, api_error_message  # noqa: E402

AGES = ["0", "10", "20", "30", "40", "50", "60", "70"]

# 저장할 열 (API 응답 항목 이름 그대로)
FIELDS = [
    "AREA_NM", "AREA_CD", "PPLTN_TIME",
    "AREA_CONGEST_LVL", "AREA_PPLTN_MIN", "AREA_PPLTN_MAX",
    "MALE_PPLTN_RATE", "FEMALE_PPLTN_RATE",
    *[f"PPLTN_RATE_{a}" for a in AGES],
    "RESNT_PPLTN_RATE", "NON_RESNT_PPLTN_RATE",
    "REPLACE_YN",
]


class PopulationCollector(ApiCollector):
    """실시간 인구데이터 (citydata_ppltn)"""

    KEY_ENV = "SEOUL_API_KEY"
    OUT_ENV = "RAW_DIR"
    DEFAULT_OUT = ROOT / "data" / "raw"
    SERVICE = "citydata_ppltn"
    TIMEOUT = 20
    RETRY_WAIT = 2
    DEDUP = ("AREA_CD", "PPLTN_TIME")      # 같은 장소·같은 측정 시각은 한 번만
    COLUMNS = FIELDS + ["COLLECTED_AT"]

    def parse(self, data: dict) -> dict:
        """응답에서 장소 기록을 찾아 FIELDS 항목만 뽑는다."""
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict) and "AREA_NM" in value[0]:
                return {f: value[0].get(f) for f in FIELDS}
        raise ApiError(api_error_message(data))


if __name__ == "__main__":
    collector = PopulationCollector.from_env()
    sys.exit(collector.run() if collector else 1)
