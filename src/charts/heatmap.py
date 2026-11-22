"""
페이지: 언제 가면 한산할까? (담당: 김경진)

[중간] 선택한 장소의 요일(월~일) × 시각(0~23) 히트맵. 혼잡도 / 인구 수 전환.
[기말] 기본 화면은 요일 하나를 골라 시간대별 막대 24개 + 추천 시간 표시, 히트맵은 '자세히 보기'로 옮긴다.
    controls(요일 선택 추가) → summary_text → render(시간대별 막대) → details(지금의 히트맵)
    예측·추천 계산은 src/recommend.py의 Recommender.hourly / best_hours / busiest_hours 사용
"""
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..models import Place
from ..recommend import WEEKDAYS, Recommender
from ..repository import PlaceRepository
from .base import BaseChart, term
from .base import CONGESTION_COLORBAR, CONGESTION_COLORS, CONGESTION_ORDER, CONGESTION_SCALE, NEUTRAL, PRIMARY


class CongestionHeatmapChart(BaseChart):
    title = "요일 × 시간 혼잡 패턴"
    owner = "김경진"

    def __init__(self) -> None:
        self.metric: str = "congestion_score"   # "congestion_score" 또는 "avg_population"
        self.weekday: int = 0                   # [기말] 고른 요일 0=월 ~ 6=일 (controls에 요일 선택 추가)

    def controls(self, repo: PlaceRepository) -> None:
        """혼잡도 / 인구 수 전환 버튼을 만들고 self.metric에 저장"""

        choice = st.radio("보기 기준", ["혼잡도", "인구 수"], key="heatmap_metric")

        if choice == "혼잡도":
            self.metric = "congestion_score"
        else:
            self.metric = "avg_population"

        day = st.selectbox("요일", WEEKDAYS, index=self.weekday, key="heatmap_weekday", help=term("예상 혼잡도"))
        self.weekday = WEEKDAYS.index(day)

    def render(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """고른 요일의 시간대별 막대 1개를 돌려준다 (_hourly_bar)"""
        if place is None or not place.records:
            return []
        return [self._hourly_bar(repo, place)]

    # ── 기말 ───────────────────────────────────────────
    def summary_text(self, repo: PlaceRepository, place: Optional[Place]) -> str:
        """
        고른 요일에서 가장 붐비는 시간 1개와 가장 한산한 시간 1개를 한 문장으로 (7~22시 기준).
          r = Recommender(repo);  r.busiest_hours(place, self.weekday, 1),  r.best_hours(place, self.weekday, 1)
          "{장소} {요일}요일은 {붐비는 시}시가 가장 붐비고, {한산한 시}시가 가장 한산해요"

        확인 (가짜 데이터): 샘플_강남역 월 → "샘플_강남역 월요일은 17시가 가장 붐비고, 7시가 가장 한산해요"
                           샘플_서울숲 토 → 붐빔 11시, 한산 21시
        """
        if place is None or not place.records:
            return ""
        r = Recommender(repo)
        busy = r.busiest_hours(place, self.weekday, 1)
        best = r.best_hours(place, self.weekday, 1)
        if not busy or not best:
            return ""
        day = WEEKDAYS[self.weekday]
        return f"{place.name} {day}요일은 {busy[0][0]}시가 가장 붐비고, {best[0][0]}시가 가장 한산해요"

    def details(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """지금 render()에 있는 요일 × 시간 히트맵을 그대로 옮겨서 돌려준다 (혼잡도/인구 수 전환도 그대로)"""
        if place is None or not place.records:
            return []
        table = place.pivot(self.metric)
        days = ["월", "화", "수", "목", "금", "토", "일"]
        hours = [f"{h}시" for h in range(24)]
        fig = go.Figure(go.Heatmap(z=table.values, x=hours, y=days,
                                   colorscale=self._colorscale(self.metric),
                                   text=self._hover_text(place), hoverinfo="text"))
        if self.metric == "congestion_score":
            fig.update_traces(zmin=1, zmax=4, colorbar=CONGESTION_COLORBAR)
        else:
            fig.update_traces(colorbar=dict(title=dict(text="명", side="top"), thickness=14, len=0.8))
        fig.update_traces(xgap=1, ygap=1)
        fig.update_yaxes(autorange="reversed")

        label = "혼잡도" if self.metric == "congestion_score" else "평균 인구"
        return [self._apply_theme(fig, height=440, title=f"{place.name} · 요일 × 시간 {label}")]

    def _hourly_bar(self, repo: PlaceRepository, place: Place) -> go.Figure:
        """
        render()의 새 기본 그래프: 고른 요일의 0~23시 막대 24개.
          표: Recommender(repo).hourly(place, self.weekday)  (열: hour, congestion, score, level)
          막대 높이 = congestion(1~4), 색 = CONGESTION_COLORS[level]
          best_hours(place, self.weekday, 3)의 세 시간 위에 "추천" 글자 (fig.add_annotation)

        확인 (가짜 데이터, 샘플_강남역 월): 3시 1.0 여유 / 9시 2.0 보통 / 12시 3.0 약간 붐빔 / 18시 4.0 붐빔,
                                          "추천"은 7·8·9시
        """
        r = Recommender(repo)
        table = r.hourly(place, self.weekday)
        day = WEEKDAYS[self.weekday]
        colors = [CONGESTION_COLORS.get(level, NEUTRAL) for level in table["level"]]
        hover = [f"{day} {h}시 / 예상 혼잡도 {c:.1f} ({level})" if pd.notna(c) else f"{day} {h}시 / 기록 없음"
                 for h, c, level in zip(table["hour"], table["congestion"], table["level"])]
        fig = go.Figure(go.Bar(x=table["hour"], y=table["congestion"], marker_color=colors,
                               hovertext=hover, hoverinfo="text"))

        congestion = dict(zip(table["hour"], table["congestion"]))
        for hour, _ in r.best_hours(place, self.weekday, 3):
            fig.add_annotation(x=hour, y=congestion[hour], text="추천", showarrow=False, yshift=12,
                               font=dict(color=PRIMARY, size=12))

        fig.update_xaxes(tickvals=list(range(0, 24, 3)), ticktext=[f"{h}시" for h in range(0, 24, 3)])
        fig.update_yaxes(range=[0, 4.6], tickvals=[1, 2, 3, 4], ticktext=CONGESTION_ORDER)
        return self._apply_theme(fig, height=420, title=f"{place.name} · {day}요일 시간대별 예상 혼잡도")

    def _hover_text(self, place: Place) -> List[List[str]]:
        """7×24 칸마다 마우스를 올렸을 때 보일 글자 (예: "월 18시 / 혼잡도 3.5 / 인구 38,000~42,000명")"""
        score = place.pivot("congestion_score")
        pop = place.pivot("avg_population")
        days = ["월", "화", "수", "목", "금", "토", "일"]
        result = []
        for d in range(7):
            row = []
            for h in range(24):
                s = score.iloc[d, h]
                p = pop.iloc[d, h]
                if pd.isna(s):
                    text = f"{days[d]} {h}시 / 기록 없음"
                else:
                    text = f"{days[d]} {h}시 / 혼잡도 {s:.1f} / 평균 인구 {p:,.0f}명"
                row.append(text)
            result.append(row)
        return result

    def _colorscale(self, metric: str) -> list:
        """congestion_score면 CONGESTION_COLORS 4단계, avg_population이면 연한색→진한색 연속 색"""
        if metric == "congestion_score":
            # 점수 1~4를 색 척도 위치 0~1에 맞춤 (1→0, 2→1/3, 3→2/3, 4→1). 지도와 같은 공통 색
            return CONGESTION_SCALE
        return [[0, "#EEF5F8"], [1, PRIMARY]]
