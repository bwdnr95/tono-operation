#!/usr/bin/env python3
"""
TONO Embedding Injection Script (Final Version)

에어비앤비 메시지 데이터에서 추출한 게스트-호스트 메시지 쌍을
TONO의 answer_embeddings 테이블에 주입합니다.

Property Code 매핑:
- 빈틈 → LCN
- 프로방스테이 A동 → PV-A
- 프로방스테이 B동 → PV-B  
- 프로방스테이 AB동 → PV-AB
- 프로방스테이 공통 → PV (그룹 코드)

사용법:
    cd /path/to/backend
    
    # Dry run (테스트)
    python -m app.scripts.inject_airbnb_embeddings --dry-run --limit 100
    
    # 실제 주입
    python -m app.scripts.inject_airbnb_embeddings

비용 예상: ~$0.02 (OpenAI text-embedding-3-small)
"""
import json
import logging
import sys
from pathlib import Path
from typing import Optional
import time

# TONO 백엔드 모듈 임포트를 위한 경로 설정
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_embedding_pairs(filepath: str) -> list:
    """JSON 파일에서 임베딩 쌍 로드"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def inject_embeddings(
    db: Session,
    pairs: list,
    batch_size: int = 50,
    dry_run: bool = False,
) -> dict:
    """
    임베딩 쌍을 DB에 주입
    
    Args:
        db: SQLAlchemy 세션
        pairs: 임베딩 쌍 리스트
        batch_size: 배치 크기 (API rate limit 고려)
        dry_run: True면 실제 저장 없이 시뮬레이션
        
    Returns:
        통계 딕셔너리
    """
    embedding_service = EmbeddingService(db)
    
    stats = {
        'total': len(pairs),
        'processed': 0,
        'skipped_error': 0,
        'success': 0,
        'by_property': {},
    }
    
    for i, pair in enumerate(pairs):
        property_code = pair['property_code']
        guest_message = pair['guest_message']
        host_response = pair['host_response']
        thread_id = pair.get('thread_id')
        
        if dry_run:
            logger.debug(
                f"[DRY RUN] Would inject: property={property_code}, "
                f"guest_len={len(guest_message)}, host_len={len(host_response)}"
            )
            stats['success'] += 1
            stats['by_property'][property_code] = stats['by_property'].get(property_code, 0) + 1
        else:
            try:
                embedding_service.store_answer(
                    guest_message=guest_message,
                    final_answer=host_response,
                    property_code=property_code,
                    was_edited=False,  # 에어비앤비 데이터는 이미 승인된 것
                    airbnb_thread_id=thread_id,
                )
                stats['success'] += 1
                stats['by_property'][property_code] = stats['by_property'].get(property_code, 0) + 1
                
            except Exception as e:
                logger.error(f"Failed to inject embedding: {e}")
                stats['skipped_error'] += 1
        
        stats['processed'] += 1
        
        # 진행 상황 로깅
        if (i + 1) % batch_size == 0:
            logger.info(
                f"Progress: {i + 1}/{len(pairs)} "
                f"(success={stats['success']}, errors={stats['skipped_error']})"
            )
            
            # Rate limit 방지를 위한 잠시 대기
            if not dry_run:
                time.sleep(0.5)
    
    # 커밋
    if not dry_run:
        db.commit()
        logger.info("Database committed successfully")
    
    return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Inject Airbnb message embeddings into TONO')
    parser.add_argument(
        '--input', '-i',
        default='embedding_pairs_final.json',
        help='Input JSON file path (default: embedding_pairs_final.json)'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Simulate without actual DB writes or API calls'
    )
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=50,
        help='Batch size for processing (default: 50)'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Limit number of pairs to process'
    )
    
    args = parser.parse_args()
    
    # 파일 로드
    logger.info(f"Loading embedding pairs from {args.input}")
    pairs = load_embedding_pairs(args.input)
    
    if args.limit:
        pairs = pairs[:args.limit]
        logger.info(f"Limited to {len(pairs)} pairs")
    
    logger.info(f"Loaded {len(pairs)} pairs")
    
    # 통계 미리보기
    from collections import Counter
    property_counts = Counter(p['property_code'] for p in pairs)
    logger.info("Pairs by property_code:")
    for prop, count in sorted(property_counts.items()):
        logger.info(f"  {prop}: {count}")
    
    # DB 세션 생성 및 주입
    with SessionLocal() as db:
        logger.info(f"Starting injection (dry_run={args.dry_run})")
        
        stats = inject_embeddings(
            db=db,
            pairs=pairs,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        
        logger.info("=" * 50)
        logger.info("Injection completed!")
        logger.info(f"  Total pairs: {stats['total']}")
        logger.info(f"  Processed: {stats['processed']}")
        logger.info(f"  Success: {stats['success']}")
        logger.info(f"  Errors: {stats['skipped_error']}")
        logger.info("  By property:")
        for prop, count in sorted(stats['by_property'].items()):
            logger.info(f"    {prop}: {count}")


if __name__ == '__main__':
    main()
