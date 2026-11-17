"""
페이지: 근처 어디로 갈까? (담당: 김재겸) — 기말 추가

위치(장소 이름이나 자치구)와 방문 요일·시간을 고르면, 근처 장소를 추천도(한산할수록 높음) 순으로 보여준다.
계산은 src/recommend.py의 Recommender.nearby()와 PlaceGeocoder.locate()가 해 주므로, 여기서는 화면만 만든다.

    controls       위치, 요일, 시간, 장소 분류, 반경 선택
    summary_text   "중구 근처 월요일 9시에는 샘플_명동이 가기 좋아요 (추천도 67점)"
    render         지도: 고른 위치(별) + 추천 장소(점, 혼잡 단계 색)
    details        추천 장소 표 (이름, 거리, 추천도, 혼잡 단계)
"""
import json
import math
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..models import Place
from ..recommend import WEEKDAYS, PlaceGeocoder, Recommender
from ..repository import DISTRICTS_GEOJSON, PlaceRepository
from .base import CONGESTION_COLORS, BaseChart, term
from .congestion_map import BASE_COLOR, BORDER_COLOR, SELECTED_COLOR, object_josa, subject_josa

ALL_CATEGORIES = "전체"
DEFAULT_QUERY = "중구"       # 처음 열었을 때 위치
TOP = 5                      # 추천 개수
ASPECT = 1.8                 # 지도 가로 / 세로 비율


class RecommendChart(BaseChart):
    title = "근처 추천 장소"
    owner = "김재겸"

    def __init__(self) -> None:
        self.query: str = ""                  # 위치 이름 (장소 이름 또는 자치구)
        self.weekday: int = 0                 # 0=월 ~ 6=일
        self.hour: int = 14                   # 방문 시각 (0~23)
        self.category: Optional[str] = None   # None이면 전체 분류
        self.radius_km: float = 3.0           # 찾을 반경
        self._geocoder: Optional[PlaceGeocoder] = None
        self._geocoder_repo: Optional[int] = None
        self._district_geo: Optional[dict] = None

    def controls(self, repo: PlaceRepository) -> None:
        """
        위치 · 요일 · 시간 · 분류 · 반경을 고르는 버튼을 만들고 위 self 속성에 저장한다.
        - 위치 후보: PlaceGeocoder(repo).candidates()  (장소 이름 + 자치구 이름)
        - 요일 이름: WEEKDAYS  (["월", ..., "일"], 저장은 번호 0~6)
        - 추천도 설명은 help=term("추천도")
        - key는 "rec_" 로 시작 (다른 페이지와 겹치지 않게)
        """
        options = self._geo(repo).candidates()
        if not self.query:
            self.query = DEFAULT_QUERY if DEFAULT_QUERY in options else (options[0] if options else "")
        if self.query not in options:
            options = [self.query] + options      # 직접 입력한 이름도 목록에 남겨 둔다

        c1, c2, c3 = st.columns([3, 1, 2])
        self.query = c1.selectbox("위치 (장소 이름이나 자치구)", options, index=options.index(self.query),
                                  key="rec_query", accept_new_options=True,
                                  help="목록에서 고르거나 직접 입력하세요. 장소 이름 일부만 써도 찾아요") or ""
        self.weekday = c2.selectbox("요일", range(7), index=self.weekday, key="rec_weekday",
                                    format_func=lambda i: f"{WEEKDAYS[i]}요일")
        self.hour = c3.slider("방문 시각", 0, 23, value=self.hour, key="rec_hour", format="%d시",
                              help=term("추천도"))

        c4, c5 = st.columns([1, 2])
        cats = [ALL_CATEGORIES] + repo.categories()
        chosen = c4.selectbox("장소 분류", cats, index=cats.index(self.category or ALL_CATEGORIES), key="rec_category")
        self.category = None if chosen == ALL_CATEGORIES else chosen
        self.radius_km = c5.slider("찾을 반경", 0.5, 10.0, value=float(self.radius_km), step=0.5,
                                   key="rec_radius", format="%.1fkm")

    def summary_text(self, repo: PlaceRepository, place: Optional[Place]) -> str:
        """
        1등 장소를 한 문장으로.
          "{위치} 근처 {요일}요일 {시}시에는 {1등 이름}이 가기 좋아요 (추천도 {점수}점)"
        위치를 못 찾으면 "'{위치}'를 찾지 못했어요", 반경 안에 장소가 없으면 "반경 {r}km 안에 장소가 없어요"

        확인 (가짜 데이터): 위치 "중구", 월요일, 9시, 전체, 5km
          → "중구 근처 월요일 9시에는 샘플_명동이 가기 좋아요 (추천도 67점)"
        """
        df = self._results(repo)
        if df is None:
            return f"'{self.query}'{object_josa(self.query)} 찾지 못했어요"
        if df.empty:
            return f"반경 {self.radius_km:g}km 안에 장소가 없어요"
        best = df.iloc[0]
        return (f"{self.query} 근처 {WEEKDAYS[self.weekday]}요일 {self.hour}시에는 "
                f"{best['name']}{subject_josa(best['name'])} 가기 좋아요 (추천도 {int(best['score'])}점)")

    def render(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """
        지도 1개: 고른 위치는 별(★), 추천 장소는 점. 점 색은 혼잡 단계(CONGESTION_COLORS[level]),
        점 위에 순위 숫자(1, 2, 3 ...). 지도 페이지와 같은 자치구 경계를 바탕으로 깔면 좋음.
        결과는 self._results(repo)로 받는다.
        """
        df = self._results(repo)
        if df is None:
            return []
        lat, lng = self._geo(repo).locate(self.query)
        circle_lat, circle_lng = self._circle(lat, lng, self.radius_km)

        fig = go.Figure()
        # 1) 자치구 경계 (지도 페이지와 같은 바탕)
        geo = self._district_geojson()
        names = [f["properties"]["name"] for f in geo["features"]]
        fig.add_trace(go.Choropleth(
            geojson=geo, featureidkey="properties.name", locations=names, z=[0] * len(names),
            colorscale=[[0, BASE_COLOR], [1, BASE_COLOR]], showscale=False,
            marker_line_color=BORDER_COLOR, marker_line_width=1, hovertemplate="%{location}<extra></extra>",
        ))
        # 2) 찾는 반경 (점선 원)
        fig.add_trace(go.Scattergeo(
            lat=circle_lat, lon=circle_lng, mode="lines", hoverinfo="skip", showlegend=False,
            line=dict(color=SELECTED_COLOR, width=1.5, dash="dot"),
        ))
        # 3) 추천 장소: 혼잡 단계 색 점 + 순위 숫자
        if not df.empty:
            fig.add_trace(go.Scattergeo(
                lat=df["lat"], lon=df["lng"], mode="markers+text", showlegend=False,
                text=[str(i + 1) for i in range(len(df))], textposition="top center",
                textfont=dict(size=14),
                marker=dict(size=16, color=[CONGESTION_COLORS[lv] for lv in df["level"]],
                            line=dict(color="white", width=1.5)),
                customdata=df[["name", "category", "distance_km", "score", "level"]],
                hovertemplate=("<b>%{text}위 %{customdata[0]}</b> (%{customdata[1]})"
                               "<br>%{customdata[2]:.2f}km · 추천도 %{customdata[3]}점 (%{customdata[4]})<extra></extra>"),
            ))
        # 4) 고른 위치 (별)
        fig.add_trace(go.Scattergeo(
            lat=[lat], lon=[lng], mode="markers", showlegend=False,
            marker=dict(symbol="star", size=20, color=SELECTED_COLOR, line=dict(color="white", width=1)),
            hovertemplate=f"<b>{self.query}</b> (고른 위치)<extra></extra>",
        ))
        # 반경 원이 꽉 차게, 가로는 화면 비율(약 16:9)에 맞춰 넓게 범위 지정
        half_lat = self.radius_km * 1.15 / 111.32
        half_lng = half_lat * ASPECT / math.cos(math.radians(lat))
        fig.update_geos(visible=False, projection_type="mercator",
                        lataxis_range=[lat - half_lat, lat + half_lat], lonaxis_range=[lng - half_lng, lng + half_lng])
        title = (f"{self.query} 반경 {self.radius_km:g}km · {WEEKDAYS[self.weekday]}요일 {self.hour}시 "
                 f"추천 {len(df)}곳")
        return [self._apply_theme(fig, height=620, title=title)]

    def details(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """추천 결과 표 1개 (go.Table): 순위, 이름, 분류, 거리(km), 추천도, 혼잡 단계"""
        df = self._results(repo)
        if df is None or df.empty:
            return []
        fig = go.Figure(go.Table(
            columnwidth=[0.6, 2.4, 1.4, 1, 1, 1.2],
            header=dict(values=["순위", "이름", "분류", "거리(km)", "추천도", "혼잡 단계"], align="left",
                        fill_color="rgba(150, 150, 150, 0.20)", font=dict(size=13)),
            cells=dict(values=[list(range(1, len(df) + 1)), df["name"], df["category"],
                               [f"{d:.2f}" for d in df["distance_km"]], [f"{int(s)}점" for s in df["score"]],
                               df["level"]],
                       align="left", height=30, fill_color="rgba(0, 0, 0, 0)",
                       font=dict(size=13)),
        ))
        return [self._apply_theme(fig, height=110 + 30 * len(df), title="추천 장소 표")]

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
        loc = self._geo(repo).locate(self.query)
        if loc is None:
            return None
        lat, lng = loc
        return Recommender(repo).nearby(lat, lng, self.weekday, self.hour, self.category, self.radius_km, top=TOP)

    # ── 내부 도우미 ────────────────────────────────────
    def _geo(self, repo: PlaceRepository) -> PlaceGeocoder:
        """위치 찾기 객체 (저장소가 바뀔 때만 새로 만든다)"""
        if self._geocoder is None or self._geocoder_repo != id(repo):
            self._geocoder, self._geocoder_repo = PlaceGeocoder(repo), id(repo)
        return self._geocoder

    def _district_geojson(self) -> dict:
        if self._district_geo is None:
            self._district_geo = json.loads(DISTRICTS_GEOJSON.read_text(encoding="utf-8"))
        return self._district_geo

    @staticmethod
    def _circle(lat: float, lng: float, radius_km: float, n: int = 72):
        """(lat, lng) 중심 반경 radius_km 원의 꼭짓점 (위도 목록, 경도 목록)"""
        dlat = radius_km / 111.32
        dlng = radius_km / (111.32 * math.cos(math.radians(lat)))
        angles = [2 * math.pi * i / n for i in range(n + 1)]
        return [lat + dlat * math.sin(a) for a in angles], [lng + dlng * math.cos(a) for a in angles]
