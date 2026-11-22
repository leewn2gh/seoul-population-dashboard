"""
예측 · 추천 · 위치 변환 (담당: 이준호)

- Predictor      : 과거 같은 요일·시간대 기록으로 예상 혼잡도(1~4)를 계산
- Recommender    : 예상 혼잡도를 추천도(0~100점)로 바꾸고, 한산한 시간·근처 장소를 골라 줌
- Geocoder       : 위치 이름 → 좌표 (추상 클래스)
  └ PlaceGeocoder: 장소 이름, 자치구 이름으로 찾기 (외부 API 없이 가진 데이터만 사용)

차트 담당은 이 파일을 수정하지 않는다. 필요한 기능은 톡방에 요청한다.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .models import Place
from .repository import DISTRICTS_GEOJSON, PlaceRepository, polygon_center

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
LEVELS = ["여유", "보통", "약간 붐빔", "붐빔"]          # 점수 1, 2, 3, 4
VISIT_HOURS = range(7, 23)                              # 추천할 때 보는 시간대 (7시 ~ 22시)


class Predictor:
    """과거 같은 요일·시간대 기록의 평균으로 예상 혼잡도를 계산한다"""

    def predict(self, place: Place, weekday: int, hour: int) -> Optional[float]:
        """
        예상 혼잡도 점수 (1 여유 ~ 4 붐빔). weekday: 0=월 ~ 6=일
        같은 요일·시간 기록이 없으면 요일 상관없이 같은 시간 기록으로, 그것도 없으면 None
        """
        same = [r.congestion_score() for r in place.records if r.time.weekday() == weekday and r.time.hour == hour]
        if not same:
            same = [r.congestion_score() for r in place.records if r.time.hour == hour]
        return sum(same) / len(same) if same else None

    @staticmethod
    def level(score: Optional[float]) -> str:
        """점수 → 가장 가까운 혼잡 단계 이름 (None이면 "정보 없음")"""
        if score is None:
            return "정보 없음"
        return LEVELS[min(4, max(1, round(score))) - 1]


class Recommender:
    """예상 혼잡도를 추천도로 바꾸고, 한산한 시간대와 근처 장소를 추천한다"""

    def __init__(self, repo: PlaceRepository, predictor: Optional[Predictor] = None):
        self.repo = repo
        self.predictor = predictor or Predictor()

    @staticmethod
    def to_score(congestion: Optional[float]) -> Optional[int]:
        """예상 혼잡도(1~4) → 추천도(0~100). 여유 100 / 보통 67 / 약간 붐빔 33 / 붐빔 0"""
        if congestion is None:
            return None
        return round((4 - congestion) / 3 * 100)

    def score(self, place: Place, weekday: int, hour: int) -> Optional[int]:
        """장소·요일·시간의 추천도 (0~100, 높을수록 한산)"""
        return self.to_score(self.predictor.predict(place, weekday, hour))

    def hourly(self, place: Place, weekday: int) -> pd.DataFrame:
        """요일 하루 24시간 예측표. 열: hour, congestion(1~4), score(0~100), level"""
        rows = []
        for h in range(24):
            c = self.predictor.predict(place, weekday, h)
            rows.append({"hour": h, "congestion": c, "score": self.to_score(c), "level": Predictor.level(c)})
        return pd.DataFrame(rows)

    def best_hours(self, place: Place, weekday: int, top: int = 3, hours=VISIT_HOURS) -> List[Tuple[int, int]]:
        """가장 한산한 시간 top개 [(시, 추천도), ...]. 추천도 높은 순, 같으면 이른 시간 순"""
        df = self.hourly(place, weekday)
        df = df[df["hour"].isin(list(hours)) & df["score"].notna()]
        df = df.sort_values(["score", "hour"], ascending=[False, True]).head(top)
        return [(int(h), int(s)) for h, s in zip(df["hour"], df["score"])]

    def busiest_hours(self, place: Place, weekday: int, top: int = 3, hours=VISIT_HOURS) -> List[Tuple[int, int]]:
        """가장 붐비는 시간 top개 [(시, 추천도), ...]. 추천도 낮은 순, 같으면 이른 시간 순"""
        df = self.hourly(place, weekday)
        df = df[df["hour"].isin(list(hours)) & df["score"].notna()]
        df = df.sort_values(["score", "hour"], ascending=[True, True]).head(top)
        return [(int(h), int(s)) for h, s in zip(df["hour"], df["score"])]

    def nearby(self, lat: float, lng: float, weekday: int, hour: int, category: Optional[str] = None,
               radius_km: float = 3.0, top: int = 5) -> pd.DataFrame:
        """
        (lat, lng)에서 radius_km 안의 장소를 추천도 높은 순으로 (같으면 가까운 순) top개.
        열: name, category, district, distance_km, congestion, score, level, lat, lng
        """
        rows = []
        for p in self.repo.by_category(category):
            d = p.distance_km(lat, lng)
            if d is None or d > radius_km:
                continue
            c = self.predictor.predict(p, weekday, hour)
            if c is None:
                continue
            rows.append({"name": p.name, "category": p.category, "district": p.district,
                         "distance_km": round(d, 2), "congestion": c, "score": self.to_score(c),
                         "level": Predictor.level(c), "lat": p.location[0], "lng": p.location[1]})
        cols = ["name", "category", "district", "distance_km", "congestion", "score", "level", "lat", "lng"]
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(rows, columns=cols)
        return df.sort_values(["score", "distance_km"], ascending=[False, True]).head(top).reset_index(drop=True)


class Geocoder(ABC):
    """위치 이름 → 좌표. 나중에 주소 검색(카카오 등)으로 바꿔도 이 형식만 지키면 나머지 코드는 그대로"""

    @abstractmethod
    def locate(self, query: str) -> Optional[Tuple[float, float]]:
        """이름에 맞는 (위도, 경도). 못 찾으면 None"""

    def candidates(self) -> List[str]:
        """검색창 자동완성용 이름 목록 (기본: 없음)"""
        return []


class PlaceGeocoder(Geocoder):
    """장소 이름 또는 자치구 이름으로 좌표를 찾는다 (외부 API 없음)"""

    def __init__(self, repo: PlaceRepository, districts_file: Path = DISTRICTS_GEOJSON):
        self.places: Dict[str, Tuple[float, float]] = {p.name: p.location for p in repo.all() if p.location}
        self.districts: Dict[str, Tuple[float, float]] = {}
        if Path(districts_file).exists():
            for f in json.loads(Path(districts_file).read_text(encoding="utf-8"))["features"]:
                self.districts[f["properties"]["name"]] = polygon_center(f["geometry"])

    def locate(self, query: str) -> Optional[Tuple[float, float]]:
        q = (query or "").strip()
        if not q:
            return None
        if q in self.places:                                   # 1) 장소 이름 그대로
            return self.places[q]
        for name in (q, q + "구"):                             # 2) 자치구 이름 ("강남", "강남구")
            if name in self.districts:
                return self.districts[name]
        for name in sorted(self.places):                       # 3) 장소 이름 일부 ("강남역" → "강남역")
            if q in name:
                return self.places[name]
        return None

    def candidates(self) -> List[str]:
        return sorted(self.places) + sorted(self.districts)
