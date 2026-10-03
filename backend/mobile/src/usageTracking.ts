/**
 * 이용 기록 기능: 자동 측정 업로드, 수기 기록, 이용 확인 알림.
 * 화면(UI)은 아직 없으며 화면에서 이 함수들을 호출하면 됩니다.
 */
import * as Notifications from "expo-notifications";
import * as UsageStats from "../modules/usage-stats";

const API_URL = process.env.EXPO_PUBLIC_API_URL;

export type Device = "phone" | "tablet" | "tv" | "pc" | "other";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API_URL + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status} ${await response.text()}`);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

// ---------- 자동 측정 (Android 전용) ----------

export type SyncResult =
  | { status: "synced"; created: number; updated: number; deleted: number; unmatched_packages: string[] }
  | { status: "skipped"; reason: "unsupported" | "no-permission" | "disabled" | "no-linked-apps" };

/**
 * 최근 days일의 앱 사용 시간을 읽어 서버에 올립니다.
 * 앱이 켜질 때와 백그라운드에서 돌아올 때(AppState "active") 호출하세요.
 * 같은 날짜를 여러 번 올려도 서버가 덮어쓰므로 중복되지 않습니다.
 */
export async function syncAutoUsage(days = 7): Promise<SyncResult> {
  if (!UsageStats.isSupported) return { status: "skipped", reason: "unsupported" };
  if (!UsageStats.hasPermission()) return { status: "skipped", reason: "no-permission" };
  const settings = await api<{ auto_tracking_enabled: boolean }>("/api/settings");
  if (!settings.auto_tracking_enabled) return { status: "skipped", reason: "disabled" };

  const subscriptions = await api<{ android_package: string | null }[]>("/api/subscriptions");
  const packages = subscriptions.flatMap((s) => (s.android_package ? [s.android_package] : []));
  if (packages.length === 0) return { status: "skipped", reason: "no-linked-apps" };

  const usage = await UsageStats.getDailyUsage(packages, days);
  const result = await api<Omit<Extract<SyncResult, { status: "synced" }>, "status">>(
    "/api/usage-logs/sync",
    {
      method: "POST",
      body: JSON.stringify({
        entries: usage.map((u) => ({
          package_name: u.packageName,
          used_date: u.date,
          duration_minutes: Math.min(u.minutes, 1440),
        })),
      }),
    },
  );
  return { status: "synced", ...result };
}

/** 설정 화면의 "자동 이용 측정" 토글. 켤 때 권한이 없으면 권한 설정 화면을 엽니다. */
export async function setAutoTracking(enabled: boolean): Promise<boolean> {
  if (enabled && !UsageStats.isSupported) return false;
  if (enabled && !UsageStats.hasPermission()) {
    UsageStats.openPermissionSettings();
    return false; // 사용자가 허용하고 돌아온 뒤 다시 호출합니다.
  }
  await api("/api/settings", { method: "PATCH", body: JSON.stringify({ auto_tracking_enabled: enabled }) });
  return enabled;
}

export const autoTrackingSupported = UsageStats.isSupported;
export const hasUsagePermission = UsageStats.hasPermission;

// ---------- 수기 기록 ----------

export function addManualUsage(
  subscriptionId: number,
  input: { usedDate?: string; device?: Device; durationMinutes?: number; memo?: string },
) {
  return api(`/api/subscriptions/${subscriptionId}/usage-logs`, {
    method: "POST",
    body: JSON.stringify({
      used_date: input.usedDate,
      device: input.device,
      duration_minutes: input.durationMinutes,
      memo: input.memo,
      source: "manual",
    }),
  });
}

// ---------- 이용 확인 알림 ----------

const CHECK_ID = "usage-check-daily";
const CHANNEL_ID = "usage-check";

export type UsageCheck = {
  enabled: boolean;
  check_time: string;
  date: string;
  items: { subscription_id: number; name: string; auto_tracked: boolean; today_auto_minutes: number | null }[];
};

/**
 * 매일 정해진 시간(설정의 usage_check_time)에 "오늘 이용하셨나요?" 알림을 예약합니다.
 * 앱 시작 시와 설정을 바꾼 뒤 호출하세요. 알림을 누르면 getUsageChecks()로 목록을 보여줍니다.
 */
export async function scheduleUsageCheck(): Promise<void> {
  await Notifications.cancelScheduledNotificationAsync(CHECK_ID).catch(() => undefined);
  const check = await api<UsageCheck>("/api/usage-checks");
  if (!check.enabled) return;

  const permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) return;
  await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
    name: "이용 확인",
    importance: Notifications.AndroidImportance.DEFAULT,
  });

  const [hour, minute] = check.check_time.split(":").map(Number);
  await Notifications.scheduleNotificationAsync({
    identifier: CHECK_ID,
    content: {
      title: "오늘 구독 서비스 이용하셨나요?",
      body: "TV나 태블릿으로 본 것도 기록해 두면 해지 추천이 정확해져요.",
      data: { type: "usage-check" },
    },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour, minute, channelId: CHANNEL_ID },
  });
}

/** 알림을 눌렀을 때 물어볼 구독 목록 (오늘 아직 기록하지 않은 활성 구독) */
export function getUsageChecks() {
  return api<UsageCheck>("/api/usage-checks");
}

/** 알림 목록에서 "봤어요"를 누른 경우. "안 봤어요"는 아무것도 기록하지 않습니다. */
export function answerUsageCheck(subscriptionId: number, device: Device, durationMinutes?: number) {
  return api(`/api/subscriptions/${subscriptionId}/usage-logs`, {
    method: "POST",
    body: JSON.stringify({ source: "notification", device, duration_minutes: durationMinutes }),
  });
}
