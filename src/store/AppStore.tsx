import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Alert } from 'react-native';
import { DEFAULT_SETTINGS, type Settings, type Subscription, type UsageLog } from '@/domain/types';
import { createApiRepository } from './apiRepository';
import { localRepository, type NewSubscription, type Repository } from './repository';

// .env.local 등에 EXPO_PUBLIC_API_URL이 있으면 서버에, 없으면 이 기기에만 저장한다.
const API_URL = process.env.EXPO_PUBLIC_API_URL;
const defaultRepository = API_URL ? createApiRepository(API_URL) : localRepository;

interface AppStore {
  ready: boolean;
  /** 처음 불러오기에 실패했을 때의 안내 문구 */
  loadError: string | null;
  reload(): void;
  onboarded: boolean;
  subscriptions: Subscription[];
  usageLogs: UsageLog[];
  settings: Settings;
  updateSettings(patch: Partial<Settings>): Promise<void>;
  completeOnboarding(): Promise<void>;
  addSubscription(input: NewSubscription): Promise<void>;
  updateSubscription(id: string, patch: Partial<Subscription>): Promise<void>;
  removeSubscription(id: string): Promise<void>;
  /** PRD F2: 원탭 체크인 */
  checkIn(subscriptionId: string, note?: string): Promise<void>;
  resetAll(): Promise<void>;
}

const Ctx = createContext<AppStore | null>(null);

const messageOf = (e: unknown) => (e instanceof Error ? e.message : '알 수 없는 오류가 났어요.');

/** 저장 실패는 화면마다 처리하지 않고 여기서 한 번에 알린다 */
async function guarded(task: () => Promise<void>) {
  try {
    await task();
  } catch (e) {
    Alert.alert('저장하지 못했어요', messageOf(e));
  }
}

export function AppStoreProvider({
  children,
  repo = defaultRepository,
}: {
  children: ReactNode;
  repo?: Repository;
}) {
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadCount, setLoadCount] = useState(0);
  const [onboarded, setOnboarded] = useState(false);
  const [subscriptions, setSubs] = useState<Subscription[]>([]);
  const [usageLogs, setLogs] = useState<UsageLog[]>([]);
  const [settings, setSettingsState] = useState<Settings>(DEFAULT_SETTINGS);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    (async () => {
      const [o, s, st] = await Promise.all([
        repo.getOnboarded(),
        repo.loadSubscriptions(),
        repo.getSettings(),
      ]);
      const l = await repo.loadUsageLogs(s);
      if (cancelled) return;
      setSettingsState(st);
      setOnboarded(o);
      setSubs(s);
      setLogs(l);
      setReady(true);
    })().catch((e) => {
      if (!cancelled) setLoadError(messageOf(e));
    });
    return () => {
      cancelled = true;
    };
  }, [repo, loadCount]);

  const reload = useCallback(() => setLoadCount((n) => n + 1), []);

  const value = useMemo<AppStore>(
    () => ({
      ready,
      loadError,
      reload,
      onboarded,
      subscriptions,
      usageLogs,
      settings,
      updateSettings: (patch) =>
        guarded(async () => {
          setSettingsState(await repo.setSettings({ ...settings, ...patch }));
        }),
      async completeOnboarding() {
        setOnboarded(true);
        await repo.setOnboarded(true);
      },
      addSubscription: (input) =>
        guarded(async () => {
          const created = await repo.createSubscription(input);
          setSubs((prev) => [...prev, created]);
        }),
      updateSubscription: (id, patch) =>
        guarded(async () => {
          const current = subscriptions.find((s) => s.id === id);
          if (!current) return;
          const saved = await repo.updateSubscription(current, patch);
          setSubs((prev) => prev.map((s) => (s.id === id ? saved : s)));
        }),
      removeSubscription: (id) =>
        guarded(async () => {
          await repo.removeSubscription(id);
          setSubs((prev) => prev.filter((s) => s.id !== id));
        }),
      checkIn: (subscriptionId, note) =>
        guarded(async () => {
          const log = await repo.addUsageLog(subscriptionId, note);
          setLogs((prev) => [...prev, log]);
        }),
      resetAll: () =>
        guarded(async () => {
          await Promise.all([repo.resetData(), repo.setOnboarded(false)]);
          setSubs([]);
          setLogs([]);
          setOnboarded(false);
        }),
    }),
    [ready, loadError, reload, onboarded, subscriptions, usageLogs, settings, repo],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppStore() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAppStore must be used inside AppStoreProvider');
  return v;
}
