import { Platform } from "react-native";
import { requireOptionalNativeModule } from "expo-modules-core";

export type DailyUsage = { packageName: string; date: string; minutes: number };

type NativeUsageStats = {
  hasPermission(): boolean;
  openPermissionSettings(): void;
  getDailyUsage(packages: string[], days: number): Promise<DailyUsage[]>;
};

// iOS와 Expo Go에는 이 모듈이 없습니다. 그때는 자동 측정 없이 수기 기록만 사용합니다.
const native =
  Platform.OS === "android" ? requireOptionalNativeModule<NativeUsageStats>("UsageStats") : null;

export const isSupported = native != null;

export function hasPermission(): boolean {
  return native?.hasPermission() ?? false;
}

export function openPermissionSettings(): void {
  native?.openPermissionSettings();
}

export async function getDailyUsage(packages: string[], days = 7): Promise<DailyUsage[]> {
  if (!native) return [];
  return native.getDailyUsage(packages, days);
}
