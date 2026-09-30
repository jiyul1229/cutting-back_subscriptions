// 백엔드(김예영)와 합의할 데이터 모델 초안. API 명세가 나오면 여기부터 맞춘다.

export type Category =
  | 'book'
  | 'ott'
  | 'shopping'
  | 'study'
  | 'lifestyle'
  | 'software'
  | 'etc';

export const CATEGORY_LABEL: Record<Category, string> = {
  book: '도서',
  ott: 'OTT',
  shopping: '쇼핑',
  study: '학습',
  lifestyle: '라이프스타일',
  software: '소프트웨어',
  etc: '기타',
};

/** PRD F1: 결제 주기. 시안에는 없지만 연 결제 구독을 표현하려면 필요함 */
export type BillingCycle = 'monthly' | 'yearly';

/** PRD F5: 유지/해지/보류 태그 */
export type Decision = 'none' | 'keep' | 'cancel' | 'hold';

export interface Subscription {
  id: string;
  name: string;
  /** 1회 결제 금액(원) */
  amount: number;
  cycle: BillingCycle;
  /** 결제일 (1~31). 해당 월에 없는 날짜면 말일로 처리 */
  billingDay: number;
  /** cycle === 'yearly'일 때 결제 월 (1~12) */
  billingMonth?: number;
  category: Category;
  memo: string;
  /** 시안의 '해지하면 매년 얼마를 절약할 수 있어요' 토글 */
  showSavings: boolean;
  /** 이용 빈도 경고 대상 여부 (보험료 등은 false — PRD 예외 흐름) */
  trackUsage: boolean;
  decision: Decision;
  createdAt: string; // ISO
}

/** PRD F2: 원탭 체크인 + 메모 */
export interface UsageLog {
  id: string;
  subscriptionId: string;
  at: string; // ISO
  note?: string;
}

/** PRD F3: 저이용 경고 */
export interface LowUsageWarning {
  subscriptionId: string;
  usesIn90Days: number;
  /** 월 요금 ÷ 이용 횟수. 이용 0회면 null */
  costPerUse: number | null;
  reasons: string[];
}
