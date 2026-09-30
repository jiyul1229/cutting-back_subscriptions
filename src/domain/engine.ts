// 코어 엔진(최지율 담당) — UI/저장소에 의존하지 않는 순수 함수만 둔다.
// 화면은 이 함수들의 결과만 받아 그린다. 로직을 바꿔도 UI 코드는 안 바뀌어야 함.

import type { AppNotification, LowUsageWarning, Settings, Subscription, UsageLog } from './types';

const DAY = 24 * 60 * 60 * 1000;

/** 월 환산 금액 */
export function monthlyAmount(s: Subscription): number {
  return s.cycle === 'yearly' ? Math.round(s.amount / 12) : s.amount;
}

export function totalMonthly(subs: Subscription[]): number {
  return subs.reduce((sum, s) => sum + monthlyAmount(s), 0);
}

export function totalYearly(subs: Subscription[]): number {
  return subs.reduce(
    (sum, s) => sum + (s.cycle === 'yearly' ? s.amount : s.amount * 12),
    0,
  );
}

function clampDay(year: number, month0: number, day: number): Date {
  const last = new Date(year, month0 + 1, 0).getDate();
  return new Date(year, month0, Math.min(day, last));
}

/** 오늘 이후(오늘 포함) 가장 가까운 결제일 */
export function nextBillingDate(s: Subscription, today = new Date()): Date {
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (s.cycle === 'monthly') {
    const thisMonth = clampDay(t.getFullYear(), t.getMonth(), s.billingDay);
    return thisMonth >= t
      ? thisMonth
      : clampDay(t.getFullYear(), t.getMonth() + 1, s.billingDay);
  }
  const m0 = (s.billingMonth ?? 1) - 1;
  const thisYear = clampDay(t.getFullYear(), m0, s.billingDay);
  return thisYear >= t ? thisYear : clampDay(t.getFullYear() + 1, m0, s.billingDay);
}

/** PRD F4: 해지 권장 기간 = [다음 결제일 - daysBefore, 다음 결제일 - 1일] */
export function cancelWindow(s: Subscription, today = new Date(), daysBefore = 5) {
  const due = nextBillingDate(s, today);
  return {
    due,
    start: new Date(due.getTime() - daysBefore * DAY),
    end: new Date(due.getTime() - DAY),
  };
}

export function usageCount(
  logs: UsageLog[],
  subscriptionId: string,
  days: number,
  today = new Date(),
): number {
  const from = today.getTime() - days * DAY;
  return logs.filter(
    (l) => l.subscriptionId === subscriptionId && new Date(l.at).getTime() >= from,
  ).length;
}

// TODO(코어 엔진): 메모 텍스트 부정 신호 분석(LLM/키워드), F6 민감도 조정 반영
const NEGATIVE_KEYWORDS = ['안 봄', '안봄', '재미없', '안 씀', '안씀', '해지'];

/** PRD F3 초안: 90일 이용 0~2회 → 후보, 메모 부정 신호는 보조 근거 */
export function detectLowUsage(
  subs: Subscription[],
  logs: UsageLog[],
  today = new Date(),
  opts = { maxUses: 2, minObservationDays: 30 },
): LowUsageWarning[] {
  return subs
    .filter((s) => s.trackUsage && s.decision !== 'cancel')
    // 등록 직후엔 기록이 없어 무조건 0회 → 관찰 기간이 지나야 경고
    // TODO(코어 엔진): 관찰 기간 < 90일일 때 이용 횟수를 기간 비율로 보정할지 결정
    .filter((s) => today.getTime() - new Date(s.createdAt).getTime() >= opts.minObservationDays * DAY)
    .map((s) => {
      const uses = usageCount(logs, s.id, 90, today);
      const reasons: string[] = [];
      if (uses <= opts.maxUses) reasons.push(`최근 90일 이용 ${uses}회`);
      const notes = logs
        .filter((l) => l.subscriptionId === s.id && l.note)
        .map((l) => l.note!);
      if (notes.some((n) => NEGATIVE_KEYWORDS.some((k) => n.includes(k)))) {
        reasons.push('메모에 부정적인 표현이 있어요');
      }
      const monthlyUses = uses / 3;
      return {
        subscriptionId: s.id,
        usesIn90Days: uses,
        costPerUse: monthlyUses > 0 ? Math.round(monthlyAmount(s) / monthlyUses) : null,
        reasons,
      };
    })
    .filter((w) => w.usesIn90Days <= opts.maxUses);
}

/** 캘린더용: 해당 월(month0: 0~11)에 결제되는 구독을 날짜별로 묶는다 */
export function billingsInMonth(
  subs: Subscription[],
  year: number,
  month0: number,
): Map<number, Subscription[]> {
  const map = new Map<number, Subscription[]>();
  for (const s of subs) {
    if (s.decision === 'cancel') continue;
    if (s.cycle === 'yearly' && (s.billingMonth ?? 1) - 1 !== month0) continue;
    const day = clampDay(year, month0, s.billingDay).getDate();
    map.set(day, [...(map.get(day) ?? []), s]);
  }
  return map;
}

/**
 * 앱 내 알림 목록 생성 (설정 토글 반영).
 * 실제 푸시는 expo-notifications로 같은 규칙을 스케줄링하면 된다.
 */
export function buildNotifications(
  subs: Subscription[],
  logs: UsageLog[],
  settings: Settings,
  today = new Date(),
  opts = { billingWithinDays: 3, cancelDaysBefore: 5 },
): AppNotification[] {
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const out: AppNotification[] = [];

  if (settings.notifications) {
    for (const s of subs) {
      if (s.decision === 'cancel') continue;
      const w = cancelWindow(s, t, opts.cancelDaysBefore);
      const dDay = Math.round((w.due.getTime() - t.getTime()) / DAY);
      if (dDay <= opts.billingWithinDays) {
        out.push({
          id: `billing-${s.id}`,
          kind: 'billing',
          subscriptionId: s.id,
          title: dDay === 0 ? `오늘 ${s.name} 결제일이에요` : `${s.name} 결제 D-${dDay}`,
          body: `${formatWon(s.amount)}이 결제될 예정이에요.`,
          date: t.toISOString(),
        });
      } else if (t >= w.start && t <= w.end) {
        out.push({
          id: `cancel-${s.id}`,
          kind: 'cancelWindow',
          subscriptionId: s.id,
          title: `${s.name} 해지 권장 기간이에요`,
          body: `${w.due.getMonth() + 1}/${w.due.getDate()} 결제 전에 해지 여부를 정해보세요.`,
          date: t.toISOString(),
        });
      }
    }
  }

  if (settings.recommendations) {
    for (const warn of detectLowUsage(subs, logs, t)) {
      const s = subs.find((x) => x.id === warn.subscriptionId)!;
      out.push({
        id: `low-${s.id}`,
        kind: 'lowUsage',
        subscriptionId: s.id,
        title: `${s.name}, 잘 쓰고 있나요?`,
        body:
          warn.reasons.join(' · ') +
          (warn.costPerUse !== null ? ` · 이용 단가 ${formatWon(warn.costPerUse)}/회` : ''),
        date: t.toISOString(),
      });
    }
  }
  return out;
}

export const formatWon = (n: number) => `${n.toLocaleString('ko-KR')}원`;
