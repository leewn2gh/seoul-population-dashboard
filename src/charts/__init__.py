"""대시보드 페이지 순서 = PAGES 순서 (담당: 이준호, 수정 금지)"""
from .congestion_map import CongestionMapChart
from .heatmap import CongestionHeatmapChart
from .recommend import RecommendChart
from .visitor import VisitorChart
from .youth import YouthChart

PAGES = {
    "지금 어디가 붐빌까?": CongestionMapChart,
    "근처 어디로 갈까?": RecommendChart,
    "언제 가면 한산할까?": CongestionHeatmapChart,
    "누가 주로 올까?": YouthChart,
    "주민이 많을까, 방문객이 많을까?": VisitorChart,
}
