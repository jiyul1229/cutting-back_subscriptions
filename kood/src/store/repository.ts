// 저장소 추상화. 지금은 로컬(AsyncStorage) — PRD '로컬 저장 기본'.
// 백엔드 API가 나오면 ApiRepository를 같은 인터페이스로 만들고 index에서 교체만 하면 된다.

import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Subscription, UsageLog } from '@/domain/types';

export interface Repository {
  loadSubscriptions(): Promise<Subscription[]>;
  saveSubscriptions(subs: Subscription[]): Promise<void>;
  loadUsageLogs(): Promise<UsageLog[]>;
  saveUsageLogs(logs: UsageLog[]): Promise<void>;
  getOnboarded(): Promise<boolean>;
  setOnboarded(v: boolean): Promise<void>;
}

const KEY = {
  subs: 'kood/subscriptions',
  logs: 'kood/usageLogs',
  onboarded: 'kood/onboarded',
};

async function readJson<T>(key: string, fallback: T): Promise<T> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const localRepository: Repository = {
  loadSubscriptions: () => readJson(KEY.subs, []),
  saveSubscriptions: (subs) => AsyncStorage.setItem(KEY.subs, JSON.stringify(subs)),
  loadUsageLogs: () => readJson(KEY.logs, []),
  saveUsageLogs: (logs) => AsyncStorage.setItem(KEY.logs, JSON.stringify(logs)),
  getOnboarded: () => readJson(KEY.onboarded, false),
  setOnboarded: (v) => AsyncStorage.setItem(KEY.onboarded, JSON.stringify(v)),
};
