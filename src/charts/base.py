"""
차트 공통 규칙 (담당: 이준호)

모든 차트는 BaseChart를 상속하고 render()를 구현한다. 나머지는 필요한 것만 구현한다.
DashboardApp은 차트 종류와 상관없이 아래 순서로 호출한다.

    controls(repo)              조작 버튼
    summary_text(repo, place)   한 문장 요약 (그래프 위에 크게)          ← 기말 추가
    summary_cards(place)        숫자 카드
    render(repo, place)         기본 그래프 (누구나 바로 이해하는 것)
    detail_controls(repo)       "자세히 보기" 안의 조작 버튼            ← 기말 추가
    details(repo, place)        "자세히 보기" 안의 그래프 (분석용)      ← 기말 추가

용어 설명은 GLOSSARY에 모아 두고, 조작 버튼의 help=term("혼잡도") 처럼 쓴다.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import plotly.graph_objects as go

from ..models import Place
from ..repository import PlaceRepository

# 혼잡도 색 (모든 차트 공통)
CONGESTION_COLORS = {"여유": "#2E9E5B", "보통": "#E6B820", "약간 붐빔": "#EE8A2E", "붐빔": "#D64545"}
CONGESTION_ORDER = ["여유", "보통", "약간 붐빔", "붐빔"]
# 혼잡도 점수(1~4)를 칠할 때 쓰는 연속 색 (지도·히트맵 공통). zmin=1, zmax=4와 함께 사용
CONGESTION_SCALE = [[i / 3, CONGESTION_COLORS[level]] for i, level in enumerate(CONGESTION_ORDER)]
CONGESTION_COLORBAR = dict(tickvals=[1, 2, 3, 4], ticktext=CONGESTION_ORDER, thickness=14, len=0.8)

# 대시보드 기본 색
PRIMARY = "#0A6B91"        # 기본 (진한 파랑)
PRIMARY_LIGHT = "#8FC1D6"  # 기본 (연한 파랑)
NEUTRAL = "#8C8C8C"        # 보조 (회색)
GRID = "rgba(128, 128, 128, 0.25)"   # 격자선 (반투명이라 라이트·다크 모드 둘 다 보임)
CLEAR = "rgba(0, 0, 0, 0)"            # 투명 배경
# 장소 분류 색 (분류로 색을 나누는 모든 차트 공통)
CATEGORY_COLORS = {"관광특구": "#0A6B91", "고궁·문화유산": "#8E6BB8", "인구밀집지역": "#D64545",
                   "발달상권": "#EE8A2E", "공원": "#2E9E5B", "미분류": "#8C8C8C"}

# 용어 설명 (사이드바 "용어 설명"과 각 조작 버튼의 help에 같이 쓰임)
GLOSSARY = {
    "혼잡도": "서울시가 실시간 인구를 보고 정한 4단계 (여유 · 보통 · 약간 붐빔 · 붐빔). 점수로 바꿀 때는 여유 1 ~ 붐빔 4",
    "예상 혼잡도": "지난 기록 중 같은 요일·같은 시간대 혼잡도의 평균",
    "추천도": "예상 혼잡도를 0~100점으로 바꾼 값. 높을수록 한산함 (여유 100 · 보통 67 · 약간 붐빔 33 · 붐빔 0)",
    "평균 인구": "그 장소에 있던 인구 추정치(최소~최대)의 가운데 값을 기간 동안 평균낸 것",
    "방문자 비율": "그 장소 인구 중 그 지역에 살지 않는 사람(일하러·놀러 온 사람)의 비율",
    "거주자 비율": "그 장소 인구 중 그 지역에 사는 사람의 비율",
    "10~30대 비율": "그 장소 인구 중 10대·20대·30대 비율을 더한 값",
    "자치구 단위": "같은 구에 있는 장소들의 값을 모아서 구 전체로 보여주는 방식",
}


def term(name: str) -> str:
    """용어 설명 한 줄 (조작 버튼의 help= 에 넣는다). 없는 용어면 빈 문자열"""
    return GLOSSARY.get(name, "")


def josa(word: str, pair: str) -> str:
    """받침에 맞는 조사. pair는 "은/는", "이/가", "을/를", "과/와" 처럼 받침 있을 때/없을 때 순서
    예) josa("경복궁", "은/는") → "은",  josa("강남역", "이/가") → "이",  josa("홍대", "은/는") → "는" """
    with_batchim, without = pair.split("/")
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return with_batchim if (ord(ch) - ord("가")) % 28 else without
        if ch.isdigit():                      # 숫자로 끝나면 읽는 소리로 (0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔)
            return with_batchim if ch in "013678" else without
    return with_batchim


class BaseChart(ABC):
    title: str = "차트 제목"
    owner: str = "담당자"

    def controls(self, repo: PlaceRepository) -> None:
        """화면에 조작 버튼(st.selectbox, st.slider 등)을 만들고, 고른 값을 self 속성에 저장한다. 기본: 없음"""

    @abstractmethod
    def render(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """그래프 목록을 돌려준다. place는 사이드바에서 고른 장소(전체 비교 차트는 안 써도 됨)."""

    def summary_cards(self, place: Optional[Place]) -> Dict[str, str]:
        """그래프 위에 띄울 숫자 카드 {"이름": "값"}. 기본: 없음"""
        return {}

    def summary_text(self, repo: PlaceRepository, place: Optional[Place]) -> str:
        """그래프를 안 봐도 답이 되는 한 문장 (예: "강남역은 평일 18시가 가장 붐벼요"). 기본: 없음"""
        return ""

    def detail_controls(self, repo: PlaceRepository) -> None:
        """'자세히 보기' 안에서 details()에만 쓰는 조작 버튼. 기본: 없음"""

    def details(self, repo: PlaceRepository, place: Optional[Place]) -> List[go.Figure]:
        """'자세히 보기'를 펼쳐야 보이는 분석용 그래프 목록. 기본: 없음"""
        return []

    def _apply_theme(self, fig: go.Figure, height: int = 420, title: Optional[str] = None) -> go.Figure:
        """모든 그래프 공통 스타일. render()에서 돌려주기 전에 꼭 거친다.
        title을 주면 그 제목을, 없으면 차트 제목(self.title)을 쓴다 (그래프가 여러 개인 페이지용)
        배경은 투명, 글자색은 지정하지 않음 → Streamlit 라이트·다크 테마 색을 그대로 따름"""
        fig.update_layout(
            title=dict(text=title or self.title, font=dict(size=17), x=0, xanchor="left"),
            height=height, margin=dict(l=20, r=20, t=60, b=20),
            font=dict(family="Noto Sans KR, sans-serif", size=13),
            paper_bgcolor=CLEAR, plot_bgcolor=CLEAR,
            hoverlabel=dict(font=dict(family="Noto Sans KR, sans-serif")),
        )
        fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
        fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
        fig.update_geos(bgcolor=CLEAR)   # 지도 배경도 투명
        return fig
