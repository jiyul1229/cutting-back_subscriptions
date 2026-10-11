// 저장소 추상화. 구현은 두 가지:
// - localRepository: 이 기기(AsyncStorage)에만 저장 — PRD '로컬 저장 기본'
// - apiRepository: FastAPI 백엔드(backend/)에 저장 — EXPO_PUBLIC_API_URL이 있으면 이걸 쓴다
// 화면·AppStore는 이 인터페이스만 알면 된다.

import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Settings, Subscription, UsageLog } from '@/domain/types';
import { DEFAULT_SETTINGS } from '@/domain/types';

export type NewSubscription = Omit<Subscription, 'id' | 'createdAt' | 'decision'>;

export interface Repository {
  loadSubscriptions(): Promise<Subscription[]>;
  loadUsageLogs(subs: Subscription[]): Promise<UsageLog[]>;
  createSubscription(input: NewSubscription): Promise<Subscription>;
  /** 바뀐 필드만 patch로 받는다. 저장된 최종 구독을 돌려준다 */
  updateSubscription(current: Subscription, patch: Partial<Subscription>): Promise<Subscription>;
  removeSubscription(id: string): Promise<void>;
  /** PRD F2: 원탭 체크인 */
  addUsageLog(subscriptionId: string, note?: string): Promise<UsageLog>;
  /** 구독·이용 기록을 모두 지운다. 설정은 유지 */
  resetData(): Promise<void>;
  getSettings(): Promise<Settings>;
  setSettings(v: Settings): Promise<Settings>;
  getOnboarded(): Promise<boolean>;
  setOnboarded(v: boolean): Promise<void>;
}

const KEY = {
  subs: 'kood/subscriptions',
  logs: 'kood/usageLogs',
  onboarded: 'kood/onboarded',
  settings: 'kood/settings',
};

export async function readJson<T>(key: string, fallback: T): Promise<T> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const writeJson = (key: string, value: unknown) =>
  AsyncStorage.setItem(key, JSON.stringify(value));

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

/** 온보딩 여부는 서버가 아니라 기기마다 따로 기억한다 */
export const onboardedStore = {
  get: () => readJson(KEY.onboarded, false),
  set: (v: boolean) => writeJson(KEY.onboarded, v),
};

const loadSubs = () => readJson<Subscription[]>(KEY.subs, []);
const loadLogs = () => readJson<UsageLog[]>(KEY.logs, []);

export const localRepository: Repository = {
  loadSubscriptions: loadSubs,
  loadUsageLogs: () => loadLogs(),
  async createSubscription(input) {
    const created: Subscription = {
      ...input,
      id: uid(),
      decision: 'none',
      createdAt: new Date().toISOString(),
    };
    await writeJson(KEY.subs, [...(await loadSubs()), created]);
    return created;
  },
  async updateSubscription(current, patch) {
    const next = { ...current, ...patch };
    const subs = await loadSubs();
    await writeJson(KEY.subs, subs.map((s) => (s.id === current.id ? next : s)));
    return next;
  },
  async removeSubscription(id) {
    await writeJson(KEY.subs, (await loadSubs()).filter((s) => s.id !== id));
  },
  async addUsageLog(subscriptionId, note) {
    const log: UsageLog = { id: uid(), subscriptionId, at: new Date().toISOString(), note };
    await writeJson(KEY.logs, [...(await loadLogs()), log]);
    return log;
  },
  async resetData() {
    await Promise.all([writeJson(KEY.subs, []), writeJson(KEY.logs, [])]);
  },
  getSettings: async () => ({ ...DEFAULT_SETTINGS, ...(await readJson(KEY.settings, {})) }),
  async setSettings(v) {
    await writeJson(KEY.settings, v);
    return v;
  },
  getOnboarded: onboardedStore.get,
  setOnboarded: onboardedStore.set,
};
