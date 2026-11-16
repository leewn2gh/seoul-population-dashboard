"""
페이지: 근처 어디로 갈까? (담당: 김재겸) — 기말 추가

위치(장소 이름이나 자치구)와 방문 요일·시간을 고르면, 근처 장소를 추천도(한산할수록 높음) 순으로 보여준다.
계산은 src/recommend.py의 Recommender.nearby()와 PlaceGeocoder.locate()가 해 주므로, 여기서는 화면만 만든다.

    controls       위치, 요일, 시간, 장소 분류, 반경 선택
    summary_text   "중구 근처 월요일 9시에는 샘플_명동이 가기 좋아요 (추천도 67점)"
    render         지도: 고른 위치(별) + 추천 장소(점, 혼잡 단계 색)
    details        추천 장소 표 (이름, 거리, 추천도, 혼잡 단계)
"""
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..models import Place
from ..recommend import WEEKDAYS, PlaceGeocoder, Recommender
from ..repository import PlaceRepository
from .base import CONGESTION_COLORS, BaseChart, term

ALL_CATEGORIES = "전체"


class RecommendChart(BaseChart):
    title = "근처 추천 장소"
    owner = "김재겸"

    def __init__(self) -> None:
        self.query: str = ""                  # 위치 이름 (장소 이름 또는 자치구)
        self.weekday: int = 0                 # 0=월 ~ 6=일
        self.hour: int = 14                   # 방문 시각 (0~23)
        self.category: Optional[str] = None   # None이면 전체 분류
        self.radius_km: float = 3.0           # 찾을 반경

    def controls(self, repo: PlaceRepository) -> None:
        """
        위치 · 요일 · 시간 · 분류 · 반경을 고르는 버튼을 만들고 위 self 속성에 저장한다.
        - 위치 후보: PlaceGeocoder(repo).candidates()  (장소 이름 + 자치구 이름)
        - 요일 이름: WEEKDAYS  (["월", ..., "일"], 저장은 번호 0~6)
        - 추천도 설명은 help=term("추천도")
        - key는 "rec_" 로 시작 (다른 페이지와 겹치지 않게)
        """
        raise NotImplementedError

    def summary_text(self, repo: PlaceRepository, place: Optional[Place]) -> str:
        """
        1등 장소를 한 문장으로.
          "{위치} 근처 {요일}요일 {시}시에는 {1등 이름}이 가기 좋아요 (추천도 {점수}점)"
        위치를 못 찾으면 "'{위치}'를 찾지 못했어요", 반경 안에 장소가 없으면 "반경 {r}km 안에 장소가 없어요"

        확인 (가짜 데이터): 위치 "중구", 월요일, 9시, 전체, 5km
          → "중구 근처 월요일 9시에는 샘플_명동이 가기 좋아요 (추천도 67점)"
        """
        raise NotImplementedError

    def render(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """
        지도 1개: 고른 위치는 별(★), 추천 장소는 점. 점 색은 혼잡 단계(CONGESTION_COLORS[level]),
        점 위에 순위 숫자(1, 2, 3 ...). 지도 페이지와 같은 자치구 경계를 바탕으로 깔면 좋음.
        결과는 self._results(repo)로 받는다.
        """
        raise NotImplementedError

    def details(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """추천 결과 표 1개 (go.Table): 순위, 이름, 분류, 거리(km), 추천도, 혼잡 단계"""
        raise NotImplementedError

    def _results(self, repo: PlaceRepository) -> Optional[pd.DataFrame]:
        """
        고른 값으로 추천 표를 만든다. 위치를 못 찾으면 None.
          loc = PlaceGeocoder(repo).locate(self.query)
          Recommender(repo).nearby(lat, lng, self.weekday, self.hour, self.category, self.radius_km, top=5)

        확인 (가짜 데이터)
          "중구", 월 9시, 전체, 5km   → 샘플_명동 0.86km 67 / 샘플_덕수궁 1.54km 67 / 샘플_서울숲 4.47km 67
          "샘플_강남역", 토 14시, 10km → 1위 샘플_강남역 0.0km 67, 2위 샘플_잠실 6.62km 67, 3위 샘플_서울숲 0점
          "없는곳"                    → None
        """
        raise NotImplementedError
