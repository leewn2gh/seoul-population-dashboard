"""
서울시 실시간 도시데이터 수집기 (담당: 이준호)

도시데이터 응답은 장소 하나에 수십~수백 KB라서 원본을 매번 저장하지 않고,
장소·시각별 '요약 숫자'만 data/raw_city/YYYY-MM-DD.csv 에 저장한다.

저장 항목
- 도로소통: 소통 상태, 평균 속도
- 주차장: 주차장 수, 총 주차면, 현재 주차 대수
- 지하철: 역 수, 승하차 인원
- 버스정류소: 정류소 수, 승하차 인원
- 문화행사: 진행 중인 행사 수
- 사고통제: 사고·통제 건수

확인용으로 원본 응답 1개를 data/samples/ 에 한 번만 저장한다.

직접 실행:  SEOUL_CITYDATA_KEY=발급받은키 python collector/collect_city.py
"""
import json
import os
import sys
import threading
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_collector import ROOT, ApiCollector, ApiError, api_error_message  # noqa: E402

SIZE_WARN_MB = 5


# ── 응답 안에서 항목 찾기 (항목 위치가 바뀌어도 이름으로 찾음) ──────────
def find_key(obj, key):
    """응답 전체를 뒤져서 key 라는 이름의 첫 값을 돌려준다."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found is not None:
                return found
    return None


def find_list(obj, key):
    """key 항목을 목록으로 꺼낸다. {key: {key: [...]}} 처럼 한 번 더 감싸진 경우도 처리."""
    value = find_key(obj, key)
    if isinstance(value, dict):
        inner = value.get(key)
        value = inner if isinstance(inner, list) else [value]
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def to_num(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def first_num(obj, *keys):
    for k in keys:
        n = to_num(find_key(obj, k))
        if n is not None:
            return n
    return None


def scalars(d, prefix):
    """dict 안의 단일 값 항목만 접두어를 붙여 꺼낸다 (지하철·버스 승하차 요약용)."""
    if not isinstance(d, dict):
        return {}
    return {f"{prefix}{k}": v for k, v in d.items() if not isinstance(v, (dict, list))}


def summarize(city: dict) -> dict:
    """도시데이터 원본(CITYDATA) → 요약 한 줄"""
    parking = find_list(city, "PRK_STTS")
    subway = find_list(city, "SUB_STTS")
    bus = find_list(city, "BUS_STN_STTS")
    events = find_list(city, "EVENT_STTS")
    accidents = find_list(city, "ACDNT_CNTRL_STTS")

    capacity = [to_num(p.get("CPCTY")) for p in parking]
    parked = [to_num(p.get("CUR_PRK_CNT")) for p in parking]

    row = {
        "AREA_NM": city.get("AREA_NM"),
        "AREA_CD": city.get("AREA_CD"),
        # 도로소통
        "ROAD_TRAFFIC_IDX": find_key(city, "ROAD_TRAFFIC_IDX"),
        "ROAD_TRAFFIC_SPD": first_num(city, "ROAD_TRAFFIC_SPD", "ROAD_TRFFC_SPD"),
        "ROAD_TRAFFIC_TIME": find_key(city, "ROAD_TRFFC_TIME") or find_key(city, "ROAD_TRAFFIC_TIME"),
        # 주차장
        "PRK_CNT": len(parking),
        "PRK_CAPACITY": sum(c for c in capacity if c is not None) if parking else None,
        "PRK_CUR_CNT": sum(p for p in parked if p is not None) if any(p is not None for p in parked) else None,
        # 지하철·버스 (역/정류소 수)
        "SUB_STN_CNT": first_num(city, "SUB_STN_CNT") or len(subway),
        "BUS_STN_CNT": first_num(city, "BUS_STN_CNT") or len(bus),
        # 문화행사·사고통제
        "EVENT_CNT": len(events),
        "ACDNT_CNT": len(accidents),
    }
    # 지하철·버스 승하차 인원 요약 (응답에 있는 요약 항목을 그대로 저장)
    row.update(scalars(find_key(city, "LIVE_SUB_PPLTN"), ""))
    row.update(scalars(find_key(city, "LIVE_BUS_PPLTN"), ""))
    # 역·정류소가 없는 장소는 요약값이 빈칸으로 오므로 목록 개수(0)로 채운다
    for key, items in (("SUB_STN_CNT", subway), ("BUS_STN_CNT", bus)):
        n = to_num(row.get(key))
        row[key] = n if n is not None else len(items)
    return row


class CityDataCollector(ApiCollector):
    """실시간 도시데이터 (citydata) 요약"""

    NAME = "도시데이터"
    KEY_ENV = "SEOUL_CITYDATA_KEY"
    OUT_ENV = "CITY_RAW_DIR"
    DEFAULT_OUT = ROOT / "data" / "raw_city"
    SERVICE = "citydata"
    TIMEOUT = 40          # 응답이 커서 인구데이터보다 길게
    RETRY_WAIT = 3
    DEDUP = ("AREA_CD", "COLLECTED_AT")

    def __init__(self, *args, sample_dir: Path = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sample_dir = Path(sample_dir or os.environ.get("SAMPLE_DIR", ROOT / "data" / "samples"))
        self._sample = None
        self._lock = threading.Lock()

    def parse(self, data: dict) -> dict:
        city = data.get("CITYDATA") or find_key(data, "CITYDATA")
        if not isinstance(city, dict) or "AREA_NM" not in city:
            raise ApiError(api_error_message(data))
        with self._lock:                      # 확인용 원본은 처음 받은 1개만 기억
            if self._sample is None:
                self._sample = city
        return summarize(city)

    def after_collect(self, rows: List[dict]) -> None:
        """확인용 원본 응답을 한 번만 저장"""
        if self._sample is None:
            return
        self.sample_dir.mkdir(parents=True, exist_ok=True)
        if not any(self.sample_dir.glob("citydata_*.json")):
            path = self.sample_dir / f"citydata_{self._sample.get('AREA_CD', 'sample')}.json"
            path.write_text(json.dumps(self._sample, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"확인용 원본 저장: {path}")

    def check_file(self, path: Path) -> None:
        size_mb = path.stat().st_size / 1e6
        if size_mb > SIZE_WARN_MB:
            print(f"::warning::도시데이터 하루 파일이 {size_mb:.1f}MB 로 예상보다 큽니다: {path.name}")


if __name__ == "__main__":
    collector = CityDataCollector.from_env()
    sys.exit(collector.run() if collector else 1)
