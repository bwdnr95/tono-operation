// src/types/outcomeLabel.ts
/**
 * Outcome Label 4축 타입 정의
 * Backend: app/services/auto_reply_service.py와 동일
 */

// 답변 방식
export type ResponseOutcome =
  | 'ANSWERED_GROUNDED'    // 제공된 정보로 명확히 답함
  | 'DECLINED_BY_POLICY'   // 정책상 불가 안내
  | 'NEED_FOLLOW_UP'       // "확인 후 안내"로 마무리
  | 'ASK_CLARIFY';         // 게스트에게 추가 질문

// 운영 액션 결과
export type OperationalOutcome =
  | 'NO_OP_ACTION'              // 운영 액션 없음
  | 'OC_CREATED'                // OC 생성됨
  | 'OC_UPDATED'                // 기존 OC 갱신
  | 'OC_RESOLUTION_SUGGESTED'   // 해소 제안 생성
  | 'OC_RESOLVED';              // resolved/done 처리

// 민감도
export type SafetyOutcome =
  | 'SAFE'         // 일반 문의
  | 'SENSITIVE'    // 불만/클레임 가능성
  | 'HIGH_RISK';   // 환불/보상/법적 이슈

// 검토 강도
export type QualityOutcome =
  | 'OK_TO_SEND'        // 일반 검토로 충분
  | 'REVIEW_REQUIRED'   // 꼼꼼히 검토 권장
  | 'LOW_CONFIDENCE';   // 정보 부족/추정 많음

// Outcome Label 전체 구조
export interface OutcomeLabel {
  // 필수 4축
  response_outcome: ResponseOutcome;
  operational_outcome: OperationalOutcome[];
  safety_outcome: SafetyOutcome;
  quality_outcome: QualityOutcome;

  // 근거 필드
  used_faq_keys: string[];
  used_profile_fields: string[];
  rule_applied: string[];
  evidence_quote: string | null;
}

// Human Override 구조
export interface HumanOverride {
  applied: boolean;
  reason: string;
  actor: string;
  timestamp: string;
}

// UI 표시용 헬퍼
export const RESPONSE_OUTCOME_LABELS: Record<ResponseOutcome, string> = {
  ANSWERED_GROUNDED: '정보 기반 답변',
  DECLINED_BY_POLICY: '정책상 거절',
  NEED_FOLLOW_UP: '확인 필요',
  ASK_CLARIFY: '추가 질문',
};

export const SAFETY_OUTCOME_LABELS: Record<SafetyOutcome, string> = {
  SAFE: '안전',
  SENSITIVE: '주의 필요',
  HIGH_RISK: '고위험',
};

export const QUALITY_OUTCOME_LABELS: Record<QualityOutcome, string> = {
  OK_TO_SEND: '발송 가능',
  REVIEW_REQUIRED: '검토 필요',
  LOW_CONFIDENCE: '신뢰도 낮음',
};

export const OPERATIONAL_OUTCOME_LABELS: Record<OperationalOutcome, string> = {
  NO_OP_ACTION: '운영 액션 없음',
  OC_CREATED: 'OC 생성됨',
  OC_UPDATED: 'OC 갱신됨',
  OC_RESOLUTION_SUGGESTED: '해소 제안',
  OC_RESOLVED: 'OC 해소됨',
};
