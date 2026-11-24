"""
대시보드 (담당: 이준호)
실행: streamlit run app.py
"""
from typing import Dict, Optional

import streamlit as st

from src.charts import PAGES
from src.charts.base import GLOSSARY, BaseChart
from src.models import Place
from src.repository import PlaceRepository, load_repository


class DashboardApp:
    def __init__(self, repo: PlaceRepository, charts: Dict[str, BaseChart]):
        self.repo = repo
        self.charts = charts
        self.place: Optional[Place] = None

    def run(self) -> None:
        self.render_page(self.render_sidebar())

    def render_sidebar(self) -> str:
        st.sidebar.title("서울 인구 대시보드")
        page = st.sidebar.radio("페이지", list(self.charts))
        category = st.sidebar.selectbox("장소 분류", self.repo.categories())
        self.place = self.repo.get(st.sidebar.selectbox("장소", self.repo.names(category)))
        start, end = self.repo.period()
        with st.sidebar.expander("용어 설명"):
            for word, meaning in GLOSSARY.items():
                st.markdown(f"**{word}**  \n{meaning}")
        st.sidebar.caption(f"데이터: {start:%Y.%m.%d} ~ {end:%Y.%m.%d} · 장소 {len(self.repo.all())}곳\n\n"
                           "출처: 서울 열린데이터광장 실시간 인구데이터·도시데이터")
        return page

    def render_page(self, name: str) -> None:
        """controls → summary_text → summary_cards → render → details 순서.
        아직 구현 안 된 부분(NotImplementedError)은 건너뛰고 나머지는 그대로 보여준다."""
        chart = self.charts[name]
        st.header(name)
        missing = []

        def call(method, *args, default=None):
            try:
                return getattr(chart, method)(*args)
            except NotImplementedError:
                missing.append(method)
                return default

        call("controls", self.repo)
        text = call("summary_text", self.repo, self.place, default="")
        if text:
            st.subheader(text)
        cards = call("summary_cards", self.place, default={})
        if cards:
            for col, (k, v) in zip(st.columns(len(cards)), cards.items()):
                col.metric(k, v)
        for fig in call("render", self.repo, self.place, default=[]) or []:
            st.plotly_chart(fig, width="stretch")
        if type(chart).details is not BaseChart.details:          # details를 만든 페이지만
            with st.expander("자세히 보기"):
                call("detail_controls", self.repo)
                for fig in call("details", self.repo, self.place, default=[]) or []:
                    st.plotly_chart(fig, width="stretch")
        if missing:
            st.info(f"{chart.owner} 담당: 구현 전 ({', '.join(missing)})")
        st.caption(f"담당: {chart.owner}")


st.set_page_config(page_title="서울 인구 대시보드", layout="wide")


@st.cache_resource
def get_repo() -> PlaceRepository:
    return load_repository()


def get_charts() -> Dict[str, BaseChart]:
    """차트 객체는 접속자마다 따로 만든다 (고른 시각·분류 같은 값이 다른 접속자와 섞이지 않게)"""
    if "charts" not in st.session_state:
        st.session_state.charts = {name: cls() for name, cls in PAGES.items()}
    return st.session_state.charts


DashboardApp(get_repo(), get_charts()).run()
