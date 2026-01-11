#!/usr/bin/env python3
"""
TONO Embedding Quality Test

임베딩 데이터 품질 및 Few-shot 성능 측정

사용법:
    cd backend
    python -m app.scripts.test_embedding_quality
    
    # 특정 숙소만 테스트
    python -m app.scripts.test_embedding_quality --property 2S214
    
    # 상세 출력
    python -m app.scripts.test_embedding_quality --verbose
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional, Dict

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 테스트 케이스 - 실제 게스트가 자주 묻는 질문들
# ═══════════════════════════════════════════════════════════════

TEST_CASES = [
    # 체크인/체크아웃 관련
    ("체크인 시간이 어떻게 되나요?", "checkin"),
    ("얼리체크인 가능할까요?", "early_checkin"),
    ("레이트 체크아웃 가능한가요?", "late_checkout"),
    ("체크인 전에 짐 맡길 수 있나요?", "luggage"),
    
    # 시설/편의시설
    ("주차 가능한가요?", "parking"),
    ("주차장 있어요?", "parking"),
    ("와이파이 비밀번호 알려주세요", "wifi"),
    ("인터넷 연결이 안 돼요", "wifi_issue"),
    ("바베큐 가능한가요?", "bbq"),
    ("수영장 이용 가능한가요?", "pool"),
    
    # 물품 관련
    ("수건이 몇 개 있나요?", "towel"),
    ("드라이기 있나요?", "hairdryer"),
    ("취사도구 있나요?", "kitchen"),
    ("세탁기 사용 가능한가요?", "laundry"),
    
    # 위치/교통
    ("숙소 주소 알려주세요", "address"),
    ("공항에서 얼마나 걸리나요?", "airport"),
    ("근처 맛집 추천해주세요", "restaurant"),
    
    # 예약 관련
    ("인원 추가 가능한가요?", "guest_add"),
    ("예약 변경하고 싶어요", "modification"),
    ("환불 정책이 어떻게 되나요?", "refund"),
    
    # 문제/불만
    ("온수가 안 나와요", "hot_water"),
    ("에어컨이 안 돼요", "aircon"),
    ("청소가 안 되어 있어요", "cleaning"),
    ("소음이 너무 심해요", "noise"),
    
    # 반려동물
    ("강아지 데려가도 되나요?", "pet"),
    ("반려견 동반 가능한가요?", "pet"),
]


@dataclass
class TestResult:
    """테스트 결과"""
    query: str
    category: str
    property_code: Optional[str]
    found_count: int
    top_similarity: float
    top_match_preview: str
    has_good_match: bool  # similarity >= 0.7


def run_quality_test(
    property_code: Optional[str] = None,
    verbose: bool = False,
    min_similarity: float = 0.5,
) -> Dict:
    """
    임베딩 품질 테스트 실행
    
    Returns:
        {
            "total_tests": int,
            "hit_count": int,  # 유사도 >= 0.7인 결과가 1개 이상
            "hit_rate": float,
            "avg_top_similarity": float,
            "by_category": {...},
            "results": [TestResult, ...]
        }
    """
    db = SessionLocal()
    embedding_service = EmbeddingService(db)
    
    results = []
    category_stats = defaultdict(lambda: {"total": 0, "hits": 0, "similarities": []})
    
    try:
        # 먼저 전체 통계 출력
        stats = embedding_service.get_stats()
        logger.info("=" * 70)
        logger.info("📊 현재 임베딩 저장소 상태")
        logger.info("=" * 70)
        logger.info(f"   총 임베딩 수: {stats['total_embeddings']:,}개")
        logger.info(f"   수정됨: {stats['edited_count']:,}개")
        logger.info(f"   미수정: {stats['unedited_count']:,}개")
        logger.info("")
        logger.info("   숙소별 분포 (상위 10개):")
        sorted_props = sorted(stats['by_property'].items(), key=lambda x: -x[1])[:10]
        for prop, count in sorted_props:
            logger.info(f"      {prop}: {count:,}개")
        logger.info("")
        
        # 테스트 실행
        logger.info("=" * 70)
        logger.info("🧪 Few-shot 품질 테스트 시작")
        if property_code:
            logger.info(f"   (필터: {property_code})")
        logger.info("=" * 70)
        
        for query, category in TEST_CASES:
            similar = embedding_service.find_similar_answers(
                query_text=query,
                property_code=property_code,
                limit=3,
                min_similarity=min_similarity,
            )
            
            found_count = len(similar)
            top_sim = similar[0].similarity if similar else 0.0
            top_preview = ""
            if similar:
                ans = similar[0]
                top_preview = f"[{ans.property_code}] {ans.final_answer[:50]}..."
            
            has_good_match = top_sim >= 0.7
            
            result = TestResult(
                query=query,
                category=category,
                property_code=property_code,
                found_count=found_count,
                top_similarity=top_sim,
                top_match_preview=top_preview,
                has_good_match=has_good_match,
            )
            results.append(result)
            
            # 카테고리별 통계
            category_stats[category]["total"] += 1
            category_stats[category]["similarities"].append(top_sim)
            if has_good_match:
                category_stats[category]["hits"] += 1
            
            # 상세 출력
            if verbose:
                status = "✅" if has_good_match else ("⚠️" if found_count > 0 else "❌")
                logger.info(f"{status} [{category}] \"{query}\"")
                logger.info(f"      유사도: {top_sim:.3f}, 결과 수: {found_count}")
                if top_preview:
                    logger.info(f"      → {top_preview}")
                logger.info("")
        
        # 결과 집계
        total = len(results)
        hits = sum(1 for r in results if r.has_good_match)
        hit_rate = hits / total if total > 0 else 0
        avg_sim = sum(r.top_similarity for r in results) / total if total > 0 else 0
        
        # 요약 출력
        logger.info("")
        logger.info("=" * 70)
        logger.info("📈 테스트 결과 요약")
        logger.info("=" * 70)
        logger.info(f"   총 테스트: {total}개")
        logger.info(f"   Hit (>=0.7): {hits}개 ({hit_rate:.1%})")
        logger.info(f"   평균 유사도: {avg_sim:.3f}")
        logger.info("")
        
        # 카테고리별 결과
        logger.info("   카테고리별 Hit Rate:")
        for cat, stat in sorted(category_stats.items()):
            cat_hit_rate = stat["hits"] / stat["total"] if stat["total"] > 0 else 0
            cat_avg_sim = sum(stat["similarities"]) / len(stat["similarities"]) if stat["similarities"] else 0
            status = "✅" if cat_hit_rate >= 0.5 else "⚠️"
            logger.info(f"      {status} {cat}: {stat['hits']}/{stat['total']} ({cat_hit_rate:.0%}), avg={cat_avg_sim:.2f}")
        
        # 문제 영역 식별
        logger.info("")
        logger.info("   ⚠️ 개선 필요 영역 (Hit Rate < 50%):")
        for cat, stat in sorted(category_stats.items()):
            cat_hit_rate = stat["hits"] / stat["total"] if stat["total"] > 0 else 0
            if cat_hit_rate < 0.5:
                logger.info(f"      - {cat}")
        
        logger.info("")
        logger.info("=" * 70)
        
        return {
            "total_tests": total,
            "hit_count": hits,
            "hit_rate": hit_rate,
            "avg_top_similarity": avg_sim,
            "by_category": dict(category_stats),
            "results": results,
        }
        
    except Exception as e:
        logger.error(f"테스트 실패: {e}")
        raise
    finally:
        db.close()


def compare_properties(properties: List[str], verbose: bool = False):
    """
    여러 숙소의 임베딩 품질 비교
    """
    logger.info("=" * 70)
    logger.info("📊 숙소별 임베딩 품질 비교")
    logger.info("=" * 70)
    
    comparison = {}
    for prop in properties:
        logger.info(f"\n[{prop}] 테스트 중...")
        result = run_quality_test(property_code=prop, verbose=False)
        comparison[prop] = {
            "hit_rate": result["hit_rate"],
            "avg_similarity": result["avg_top_similarity"],
            "hit_count": result["hit_count"],
        }
    
    # 비교 결과 출력
    logger.info("\n" + "=" * 70)
    logger.info("📈 비교 결과")
    logger.info("=" * 70)
    logger.info(f"{'Property':<12} {'Hit Rate':<12} {'Avg Sim':<12} {'Hits':<8}")
    logger.info("-" * 44)
    
    for prop in sorted(comparison.keys(), key=lambda x: -comparison[x]["hit_rate"]):
        data = comparison[prop]
        logger.info(f"{prop:<12} {data['hit_rate']:.1%}{'':>6} {data['avg_similarity']:.3f}{'':>6} {data['hit_count']}")
    
    return comparison


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TONO Embedding Quality Test")
    parser.add_argument("--property", "-p", help="특정 숙소로 필터링")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 출력")
    parser.add_argument("--compare", "-c", nargs="+", help="여러 숙소 비교 (예: --compare 2S214 LCN PV)")
    
    args = parser.parse_args()
    
    if args.compare:
        compare_properties(args.compare, verbose=args.verbose)
    else:
        run_quality_test(property_code=args.property, verbose=args.verbose)
