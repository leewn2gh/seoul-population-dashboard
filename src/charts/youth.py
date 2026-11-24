"""
페이지: 누가 주로 올까? (담당: 이다혜)

[중간] 10~30대 비율이 높은 장소 상위 N개를 10대·20대·30대 누적 가로 막대로 비교한다.
[기말] 기본 화면은 고른 장소 하나의 연령대 분포, 상위 N개 비교는 '자세히 보기'로 옮긴다.
    summary_text → render(연령대 분포 막대) → details(지금의 상위 N개 그래프)
"""
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..models import AGE_GROUPS, Place
from ..repository import PlaceRepository
from .base import PRIMARY, PRIMARY_LIGHT, BaseChart, term

ALL_CATEGORIES = "전체"
# (표 열 이름, 범례 이름, 색)
AGE_BARS = [("age_10", "10대", PRIMARY_LIGHT), ("age_20", "20대", "#3D8DB0"), ("age_30", "30대", PRIMARY)]


class YouthChart(BaseChart):
    title = "10~30대 비율이 높은 장소"
    owner = "이다혜"

    def __init__(self) -> None:
        self.category: Optional[str] = None   # None이면 전체 분류
        self.top_n: int = 10

    def detail_controls(self, repo: PlaceRepository) -> None:
        """상위 N개 비교 그래프용: 장소 분류, 상위 N개"""
        choice = st.selectbox("장소 분류", [ALL_CATEGORIES] + repo.categories(), key="youth_category",
                              help=term("10~30대 비율"))
        self.category = None if choice == ALL_CATEGORIES else choice
        self.top_n = st.slider("상위 N개", min_value=5, max_value=30, value=self.top_n, key="youth_top_n",
                               help=term("10~30대 비율"))

    def render(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        if place is None or not place.records:
            st.info("연령대 분포를 보려면 장소를 선택해 주세요.")
            return []
        return [self._age_bar(place)]

    def summary_text(self, repo: PlaceRepository, place: Optional[Place]) -> str:
        """
        고른 장소에 가장 많은 연령대를 한 문장으로. place.avg_age_distribution() 사용
          "{장소}에는 {연령대}가 가장 많이 와요 ({비율:.1f}%)"

        확인 (가짜 데이터): 샘플_강남역 → "샘플_강남역에는 20대가 가장 많이 와요 (35.0%)"
                           샘플_서울숲 → 40대 29.2%
        """
        if place is None or not place.records:
            return ""
        dist = place.avg_age_distribution()
        top = max(AGE_GROUPS, key=lambda a: dist[a])   # 같으면 어린 연령대 먼저
        return f"{place.name}에는 {top}가 가장 많이 와요 ({dist[top]:.1f}%)"

    def details(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """지금 render()에 있는 '상위 N개 비교' 그래프를 그대로 옮겨서 돌려준다"""
        df = repo.summary_dataframe(self.category)
        fig = go.Figure()
        if df.empty:
            fig.add_annotation(text="표시할 장소가 없습니다", showarrow=False, font=dict(size=16))
            return [self._apply_theme(fig)]

        top = self._top_n(df, self.top_n)
        for col, label, color in AGE_BARS:
            fig.add_trace(go.Bar(
                y=top["name"], x=top[col], name=label, orientation="h",
                marker_color=color, hovertemplate=f"%{{y}}<br>{label}: %{{x:.1f}}%<extra></extra>",
            ))
        fig.update_layout(barmode="stack", legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1, xanchor="right", traceorder="normal"))
        fig.update_xaxes(title="10~30대 비율 합 (%)")
        fig.update_yaxes(autorange="reversed")   # 비율이 가장 높은 장소를 맨 위로
        scope = self.category or "전체 장소"
        return [self._apply_theme(fig, height=max(420, 40 * len(top) + 120), title=f"{self.title} · {scope} 상위 {len(top)}곳")]

    def _age_bar(self, place: Place) -> go.Figure:
        """
        render()의 새 기본 그래프: 0대 ~ 70대 8개 세로 막대 (y: 비율 %).
        가장 많은 연령대 막대만 PRIMARY, 나머지는 PRIMARY_LIGHT
        확인 (가짜 데이터, 샘플_강남역): 0대 2.0 / 10대 5.0 / 20대 35.0 / 30대 30.0 / 40대 11.2 / 50대 8.4 / 60대 5.6 / 70대 2.8
        """
        dist = place.avg_age_distribution()
        values = [dist[a] for a in AGE_GROUPS]
        top = max(AGE_GROUPS, key=lambda a: dist[a])   # summary_text와 같은 기준
        colors = [PRIMARY if a == top else PRIMARY_LIGHT for a in AGE_GROUPS]
        fig = go.Figure(go.Bar(
            x=AGE_GROUPS, y=values, marker_color=colors,
            text=[f"{v:.1f}%" for v in values], textposition="outside",
            hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
        ))
        fig.update_xaxes(title="연령대")
        fig.update_yaxes(title="비율 (%)", range=[0, max(values) * 1.15 or 1])   # 막대 위 글자가 안 잘리게
        return self._apply_theme(fig, title=f"{place.name} · 연령대 분포")

    def _top_n(self, df: pd.DataFrame, n: int) -> pd.DataFrame:
        return df.sort_values("youth_rate", ascending=False).head(n).reset_index(drop=True)
