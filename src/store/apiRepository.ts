// FastAPI 백엔드(backend/app)와 통신하는 Repository 구현.
// 서버 필드(snake_case, 정수 id)와 앱 모델(src/domain/types.ts)의 변환은 이 파일에서만 한다.

import type {
  Category,
  Decision,
  Settings,
  Subscription,
  UsageLog,
} from '@/domain/types';
import { CATEGORY_LABEL } from '@/domain/types';
import { onboardedStore, readJson, writeJson, type Repository } from './repository';

const TIMEOUT_MS = 10_000;

/** 서버 응답 모양 — backend/app/schemas.py 기준 (앱에서 쓰는 필드만) */
interface SubscriptionDto {
  id: number;
  name: string;
  price_won: number;
  billing_cycle: 'monthly' | 'yearly' | 'weekly';
  billing_day: number | null;
  billing_month: number | null;
  category: string | null;
  memo: string | null;
  track_usage: boolean;
  latest_decision: 'keep' | 'cancel' | 'hold' | null;
  created_at: string;
}

interface UsageLogDto {
  id: number;
  subscription_id: number;
  used_date: string; // YYYY-MM-DD (한국 시간 기준)
  memo: string | null;
  created_at: string;
}

interface SettingsDto {
  notifications_enabled: boolean;
  recommendation_enabled: boolean;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

// showSavings(절약액 표시 토글)는 서버에 없는 화면 설정이라 기기에만 저장한다.
const SHOW_SAVINGS_KEY = 'kood/api/showSavings';
type ShowSavingsMap = Record<string, boolean>;
const loadShowSavings = () => readJson<ShowSavingsMap>(SHOW_SAVINGS_KEY, {});
async function saveShowSavings(id: string, value: boolean) {
  await writeJson(SHOW_SAVINGS_KEY, { ...(await loadShowSavings()), [id]: value });
}

const isCategory = (v: string | null): v is Category =>
  v !== null && Object.prototype.hasOwnProperty.call(CATEGORY_LABEL, v);

function toSubscription(dto: SubscriptionDto, showSavings: ShowSavingsMap): Subscription {
  const id = String(dto.id);
  return {
    id,
    name: dto.name,
    amount: dto.price_won,
    // 앱은 매주 결제를 아직 지원하지 않는다. 서버에서 앱으로만 등록하므로 들어올 일은 없다.
    cycle: dto.billing_cycle === 'yearly' ? 'yearly' : 'monthly',
    billingDay: dto.billing_day ?? 1,
    billingMonth: dto.billing_month ?? undefined,
    category: isCategory(dto.category) ? dto.category : 'etc',
    memo: dto.memo ?? '',
    showSavings: showSavings[id] ?? true,
    trackUsage: dto.track_usage,
    decision: dto.latest_decision ?? 'none',
    createdAt: dto.created_at,
  };
}

const pad = (n: number) => String(n).padStart(2, '0');
const localDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function toUsageLog(dto: UsageLogDto): UsageLog {
  // 서버는 '이용한 날짜'만 가진다. 기록한 날 이용했다면 실제 기록 시각을, 아니면 그날 정오를 쓴다.
  const created = new Date(dto.created_at);
  const at =
    localDate(created) === dto.used_date ? dto.created_at : `${dto.used_date}T12:00:00`;
  return {
    id: String(dto.id),
    subscriptionId: String(dto.subscription_id),
    at,
    note: dto.memo ?? undefined,
  };
}

/** 앱 필드 → 서버 필드. 결제 주기 규칙(월간은 billing_month null)은 최종 값 기준으로 맞춘다 */
function toSubscriptionBody(next: Subscription, patch: Partial<Subscription>) {
  const body: Record<string, unknown> = {};
  if ('name' in patch) body.name = next.name;
  if ('amount' in patch) body.price_won = next.amount;
  if ('cycle' in patch || 'billingDay' in patch || 'billingMonth' in patch) {
    body.billing_cycle = next.cycle;
    body.billing_day = next.billingDay;
    body.billing_month = next.cycle === 'yearly' ? (next.billingMonth ?? null) : null;
  }
  if ('category' in patch) body.category = next.category;
  if ('memo' in patch) body.memo = next.memo.trim() || null;
  if ('trackUsage' in patch) body.track_usage = next.trackUsage;
  return body;
}

export function createApiRepository(baseUrl: string): Repository {
  const root = baseUrl.replace(/\/+$/, '');

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(`${root}${path}`, {
        method,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      throw new ApiError('서버에 연결할 수 없어요. 네트워크와 서버 주소를 확인해 주세요.');
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new ApiError(`요청을 처리하지 못했어요 (${res.status}) ${detail}`.trim(), res.status);
    }
    return (res.status === 204 ? undefined : await res.json()) as T;
  }

  const fetchSubscription = async (id: string) =>
    toSubscription(await request<SubscriptionDto>('GET', `/api/subscriptions/${id}`), await loadShowSavings());

  return {
    async loadSubscriptions() {
      const [dtos, showSavings] = await Promise.all([
        request<SubscriptionDto[]>('GET', '/api/subscriptions'),
        loadShowSavings(),
      ]);
      return dtos.map((d) => toSubscription(d, showSavings));
    },

    async loadUsageLogs(subs) {
      const lists = await Promise.all(
        subs.map((s) => request<UsageLogDto[]>('GET', `/api/subscriptions/${s.id}/usage-logs`)),
      );
      return lists.flat().map(toUsageLog);
    },

    async createSubscription(input) {
      const dto = await request<SubscriptionDto>('POST', '/api/subscriptions', {
        name: input.name,
        price_won: input.amount,
        billing_cycle: input.cycle,
        billing_day: input.billingDay,
        billing_month: input.cycle === 'yearly' ? (input.billingMonth ?? null) : null,
        category: input.category,
        memo: input.memo.trim() || null,
        track_usage: input.trackUsage,
      });
      await saveShowSavings(String(dto.id), input.showSavings);
      return toSubscription(dto, { [dto.id]: input.showSavings });
    },

    async updateSubscription(current, patch) {
      const next = { ...current, ...patch };
      // 결정을 먼저 기록해야 아래 PATCH/GET 응답의 latest_decision이 최신이 된다.
      if (patch.decision !== undefined && patch.decision !== current.decision) {
        await request('POST', `/api/subscriptions/${current.id}/decisions`, {
          decision: patch.decision satisfies Decision,
        });
      }
      if ('showSavings' in patch) await saveShowSavings(current.id, next.showSavings);
      const body = toSubscriptionBody(next, patch);
      if (Object.keys(body).length === 0) return fetchSubscription(current.id);
      const dto = await request<SubscriptionDto>('PATCH', `/api/subscriptions/${current.id}`, body);
      return toSubscription(dto, await loadShowSavings());
    },

    async removeSubscription(id) {
      // 서버는 숨김 처리만 하고 결제·이용 기록은 분석용으로 남긴다.
      await request('DELETE', `/api/subscriptions/${id}`);
    },

    async addUsageLog(subscriptionId, note) {
      const dto = await request<UsageLogDto>('POST', `/api/subscriptions/${subscriptionId}/usage-logs`, {
        memo: note?.trim() || null,
      });
      return toUsageLog(dto);
    },

    async resetData() {
      await request('POST', '/api/settings/reset-data', { confirm: true });
      await writeJson(SHOW_SAVINGS_KEY, {});
    },

    async getSettings() {
      const dto = await request<SettingsDto>('GET', '/api/settings');
      return { notifications: dto.notifications_enabled, recommendations: dto.recommendation_enabled };
    },

    async setSettings(v: Settings) {
      const dto = await request<SettingsDto>('PATCH', '/api/settings', {
        notifications_enabled: v.notifications,
        recommendation_enabled: v.recommendations,
      });
      return { notifications: dto.notifications_enabled, recommendations: dto.recommendation_enabled };
    },

    getOnboarded: onboardedStore.get,
    setOnboarded: onboardedStore.set,
  };
}
