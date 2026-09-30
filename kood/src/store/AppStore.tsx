import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Subscription, UsageLog } from '@/domain/types';
import { localRepository, type Repository } from './repository';

type NewSubscription = Omit<Subscription, 'id' | 'createdAt' | 'decision'>;

interface AppStore {
  ready: boolean;
  onboarded: boolean;
  subscriptions: Subscription[];
  usageLogs: UsageLog[];
  completeOnboarding(): Promise<void>;
  addSubscription(input: NewSubscription): Promise<void>;
  updateSubscription(id: string, patch: Partial<Subscription>): Promise<void>;
  removeSubscription(id: string): Promise<void>;
  /** PRD F2: 원탭 체크인 */
  checkIn(subscriptionId: string, note?: string): Promise<void>;
  resetAll(): Promise<void>;
}

const Ctx = createContext<AppStore | null>(null);

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export function AppStoreProvider({
  children,
  repo = localRepository,
}: {
  children: ReactNode;
  repo?: Repository;
}) {
  const [ready, setReady] = useState(false);
  const [onboarded, setOnboarded] = useState(false);
  const [subscriptions, setSubs] = useState<Subscription[]>([]);
  const [usageLogs, setLogs] = useState<UsageLog[]>([]);

  useEffect(() => {
    Promise.all([repo.getOnboarded(), repo.loadSubscriptions(), repo.loadUsageLogs()]).then(
      ([o, s, l]) => {
        setOnboarded(o);
        setSubs(s);
        setLogs(l);
        setReady(true);
      },
    );
  }, [repo]);

  const persistSubs = useCallback(
    async (next: Subscription[]) => {
      setSubs(next);
      await repo.saveSubscriptions(next);
    },
    [repo],
  );

  const value = useMemo<AppStore>(
    () => ({
      ready,
      onboarded,
      subscriptions,
      usageLogs,
      async completeOnboarding() {
        setOnboarded(true);
        await repo.setOnboarded(true);
      },
      async addSubscription(input) {
        await persistSubs([
          ...subscriptions,
          { ...input, id: uid(), decision: 'none', createdAt: new Date().toISOString() },
        ]);
      },
      async updateSubscription(id, patch) {
        await persistSubs(subscriptions.map((s) => (s.id === id ? { ...s, ...patch } : s)));
      },
      async removeSubscription(id) {
        await persistSubs(subscriptions.filter((s) => s.id !== id));
      },
      async checkIn(subscriptionId, note) {
        const next = [...usageLogs, { id: uid(), subscriptionId, at: new Date().toISOString(), note }];
        setLogs(next);
        await repo.saveUsageLogs(next);
      },
      async resetAll() {
        setSubs([]);
        setLogs([]);
        setOnboarded(false);
        await Promise.all([
          repo.saveSubscriptions([]),
          repo.saveUsageLogs([]),
          repo.setOnboarded(false),
        ]);
      },
    }),
    [ready, onboarded, subscriptions, usageLogs, repo, persistSubs],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppStore() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAppStore must be used inside AppStoreProvider');
  return v;
}
