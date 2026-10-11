package expo.modules.usagestats

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Process
import android.provider.Settings
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.util.Calendar
import java.util.TimeZone

class UsagePermissionException : CodedException("Usage access permission is not granted")

class UsageStatsModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("UsageStats")

    // 설정 > 사용 정보 접근 허용 여부
    Function("hasPermission") { hasPermission() }

    // 사용자가 직접 권한을 켜는 시스템 설정 화면을 엽니다.
    Function("openPermissionSettings") {
      context.startActivity(
        Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      )
    }

    // 최근 days일(오늘 포함) 동안 각 패키지의 하루 사용 시간(분). 날짜는 서버와 같은 한국 날짜입니다.
    AsyncFunction("getDailyUsage") { packages: List<String>, days: Int ->
      if (!hasPermission()) throw UsagePermissionException()
      val manager = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
      val targets = packages.toSet()
      val now = System.currentTimeMillis()
      val result = mutableListOf<Map<String, Any>>()
      for (offset in (days.coerceIn(1, 30) - 1) downTo 0) {
        val day = Calendar.getInstance(SEOUL).apply {
          timeInMillis = now
          set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0)
          set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
          add(Calendar.DAY_OF_MONTH, -offset)
        }
        val start = day.timeInMillis
        val end = minOf(
          (day.clone() as Calendar).apply { add(Calendar.DAY_OF_MONTH, 1) }.timeInMillis, now
        )
        val totals = foregroundMillis(manager, targets, start, end)
        val date = String.format(
          "%04d-%02d-%02d", day.get(Calendar.YEAR), day.get(Calendar.MONTH) + 1, day.get(Calendar.DAY_OF_MONTH)
        )
        for (packageName in targets) {
          result.add(mapOf(
            "packageName" to packageName,
            "date" to date,
            "minutes" to ((totals[packageName] ?: 0L) / 60_000L).toInt(),
          ))
        }
      }
      result
    }
  }

  private fun hasPermission(): Boolean {
    val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
    val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      appOps.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
    } else {
      @Suppress("DEPRECATION")
      appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
    }
    return mode == AppOpsManager.MODE_ALLOWED
  }

  /** 화면에 앱이 떠 있던 시간을 이벤트로 합산합니다. 자정을 넘긴 사용은 날짜별로 나뉩니다. */
  @Suppress("DEPRECATION")
  private fun foregroundMillis(
    manager: UsageStatsManager, targets: Set<String>, start: Long, end: Long
  ): Map<String, Long> {
    val totals = HashMap<String, Long>()
    val openedAt = HashMap<String, Long>()          // 패키지가 화면에 올라온 시각
    val openClasses = HashMap<String, MutableSet<String>>()  // 앱 안에서 열린 화면(Activity)들
    val seen = HashSet<String>()
    fun add(packageName: String, from: Long, to: Long) {
      if (to > from) totals[packageName] = (totals[packageName] ?: 0L) + (to - from)
    }
    fun closeAll(at: Long) {
      for ((packageName, opened) in openedAt) add(packageName, opened, at)
      openedAt.clear(); openClasses.clear()
    }

    val events = manager.queryEvents(start, end)
    val event = UsageEvents.Event()
    while (events.hasNextEvent()) {
      events.getNextEvent(event)
      val packageName = event.packageName
      when (event.eventType) {
        UsageEvents.Event.MOVE_TO_FOREGROUND -> if (packageName in targets) {
          val classes = openClasses.getOrPut(packageName) { mutableSetOf() }
          if (classes.isEmpty()) openedAt[packageName] = event.timeStamp
          classes.add(event.className ?: "")
          seen.add(packageName)
        }
        UsageEvents.Event.MOVE_TO_BACKGROUND -> if (packageName in targets) {
          val classes = openClasses[packageName]
          if (classes != null && classes.remove(event.className ?: "")) {
            if (classes.isEmpty()) openedAt.remove(packageName)?.let { add(packageName, it, event.timeStamp) }
          } else if (packageName !in seen) {
            // 자정 전에 열어 둔 앱: 이 날의 시작부터 계산
            add(packageName, start, event.timeStamp)
          }
          seen.add(packageName)
        }
        // 화면 꺼짐(16)·기기 종료(26)이면 열려 있던 앱을 모두 닫은 것으로 봅니다.
        16, 26 -> closeAll(event.timeStamp)
      }
    }
    closeAll(end)
    return totals
  }

  companion object {
    private val SEOUL: TimeZone = TimeZone.getTimeZone("Asia/Seoul")
  }
}
