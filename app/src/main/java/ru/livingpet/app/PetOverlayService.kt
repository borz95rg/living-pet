package ru.livingpet.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.util.DisplayMetrics
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Calendar
import java.util.Locale
import kotlin.math.abs

/** User-started animated fox overlay. Its idle loop pauses while the display is off. */
class PetOverlayService : Service() {
    private lateinit var windowManager: WindowManager
    private lateinit var petView: FoxPet3DView
    private lateinit var params: WindowManager.LayoutParams
    private val handler = Handler(Looper.getMainLooper())
    private var dragging = false
    private var downRawX = 0f
    private var downRawY = 0f
    private var downAt = 0L
    private var startX = 0
    private var startY = 0
    private var lastTouchAt = System.currentTimeMillis()
    private var lastWanderAt = System.currentTimeMillis()
    private var wanderUntil = 0L
    private var sleeping = false
    private var running = false
    private var direction = 1
    private var screenOn = true
    private var receiverRegistered = false

    private val save by lazy { getSharedPreferences("living_pet_save", MODE_PRIVATE) }
    private val screenReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_OFF -> pauseForScreenOff()
                Intent.ACTION_SCREEN_ON -> resumeForScreenOn()
            }
        }
    }

    private val wander = object : Runnable {
        override fun run() {
            if (!::petView.isInitialized) return
            val now = System.currentTimeMillis()
            if (screenOn && !dragging) {
                val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
                val shouldSleep = hour >= 22 || hour < 7
                if (shouldSleep != sleeping) {
                    sleeping = shouldSleep
                    petView.setSleeping(sleeping)
                    if (sleeping) {
                        wanderUntil = 0L
                        petView.setWalking(false)
                    }
                }
                if (sleeping) {
                    handler.postDelayed(this, 30_000L)
                    return
                }
                if (wanderUntil == 0L && now - lastTouchAt > 8 * 60_000L && now - lastWanderAt > 6 * 60_000L) {
                    running = kotlin.random.Random.nextInt(4) == 0
                    wanderUntil = now + if (running) 2_800L else 2_500L
                    petView.setWalking(true)
                    if (running) petView.playAction("Run", 2_800L)
                }
                if (wanderUntil > 0L && now < wanderUntil) {
                    val speedDp = if (running) 9 else 4
                    val step = (speedDp * resources.displayMetrics.density).toInt().coerceAtLeast(1)
                    val maxX = (screenBounds().width() - params.width).coerceAtLeast(0)
                    params.x += direction * step
                    if (params.x <= 0) { params.x = 0; direction = 1 }
                    if (params.x >= maxX) { params.x = maxX; direction = -1 }
                    petView.faceRight = direction > 0
                    runCatching { windowManager.updateViewLayout(petView, params) }
                } else if (wanderUntil > 0L) {
                    wanderUntil = 0L
                    lastWanderAt = now
                    petView.setWalking(false)
                    if (kotlin.random.Random.nextInt(4) == 0) petView.playAction("Jump", 900L)
                }
                handler.postDelayed(this, if (sleeping) 30_000L else 500L)
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        createNotificationChannel()
        screenOn = (getSystemService(POWER_SERVICE) as PowerManager).isInteractive
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_OFF)
            addAction(Intent.ACTION_SCREEN_ON)
        }
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(screenReceiver, filter, Context.RECEIVER_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(screenReceiver, filter)
        }
        receiverRegistered = true
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (!Settings.canDrawOverlays(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, buildNotification(), android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, buildNotification())
        }
        if (!::petView.isInitialized) showFox()
        return START_NOT_STICKY
    }

    private fun showFox() {
        val state = try { JSONObject(save.getString("state_v1", "") ?: "") } catch (_: Exception) { JSONObject() }
        if (state.optString("kind", "") != "fox") {
            stopSelf()
            return
        }
        val xp = state.optInt("xp", 0).coerceIn(0, 32)
        val stage = (xp / 8).coerceAtMost(4)
        val density = resources.displayMetrics.density
        val width = (205 * density).toInt()
        val height = (198 * density).toInt()
        petView = FoxPet3DView(this, stage).apply {
            setAnimationEnabled(screenOn)
            setTouchHandler { event -> handleTouch(event) }
        }
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        sleeping = hour >= 22 || hour < 7
        petView.setSleeping(sleeping)
        params = WindowManager.LayoutParams(
            width, height,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            val bounds = screenBounds()
            x = save.getInt("overlay_x", (bounds.width() - width) / 2).coerceIn(0, (bounds.width() - width).coerceAtLeast(0))
            y = save.getInt("overlay_y", (bounds.height() - height - (90 * density).toInt()).coerceAtLeast(0)).coerceIn(0, (bounds.height() - height).coerceAtLeast(0))
        }
        try {
            windowManager.addView(petView, params)
            save.edit().putBoolean("overlay_enabled", true).apply()
            if (screenOn) handler.post(wander)
        } catch (_: SecurityException) {
            stopSelf()
        }
    }

    private fun handleTouch(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downRawX = event.rawX; downRawY = event.rawY
                startX = params.x; startY = params.y
                downAt = System.currentTimeMillis()
                dragging = false
                lastTouchAt = downAt
                petView.setWalking(false)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = (event.rawX - downRawX).toInt()
                val dy = (event.rawY - downRawY).toInt()
                val density = resources.displayMetrics.density
                if (abs(dx) + abs(dy) > 8 * density) dragging = true
                if (dragging) {
                    val bounds = screenBounds()
                    params.x = (startX + dx).coerceIn(0, (bounds.width() - params.width).coerceAtLeast(0))
                    params.y = (startY + dy).coerceIn(0, (bounds.height() - params.height).coerceAtLeast(0))
                    petView.onDragged(dx)
                    runCatching { windowManager.updateViewLayout(petView, params) }
                }
                return true
            }
            MotionEvent.ACTION_UP -> {
                if (dragging) {
                    save.edit().putInt("overlay_x", params.x).putInt("overlay_y", params.y).apply()
                } else if (System.currentTimeMillis() - downAt > 650L) {
                    startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP))
                } else {
                    petView.reactAt(event.x, event.y)
                    recordPetTouch()
                }
                dragging = false
                lastTouchAt = System.currentTimeMillis()
                return true
            }
            MotionEvent.ACTION_CANCEL -> { dragging = false; return true }
        }
        return true
    }

    /** Persist overlay petting into the same versioned save used by the game screen. */
    private fun recordPetTouch() {
        val state = try { JSONObject(save.getString("state_v1", "") ?: "") } catch (_: Exception) { return }
        if (state.optString("kind") != "fox") return
        val time = System.currentTimeMillis()
        val needs = state.optJSONObject("needs") ?: JSONObject().apply {
            put("satiety", 90); put("water", 85); put("energy", 90)
            put("mood", 80); put("health", 100); put("clean", 95); put("affection", 8)
        }
        needs.put("mood", (needs.optDouble("mood", 80.0) + 4.0).coerceAtMost(100.0))
        needs.put("affection", (needs.optDouble("affection", 8.0) + 4.0).coerceAtMost(100.0))
        state.put("needs", needs)
        state.put("lastInteractionAt", time)
        state.put("updatedAt", time)
        state.put("version", 3)
        state.put("lastLine", "Мне приятно, что ты меня погладил. Хорошо, что ты рядом!")
        state.put("bubble", "приятно! 💛")

        val routine = state.optJSONObject("routine") ?: JSONObject()
        routine.put("petting", routine.optInt("petting", 0) + 1)
        state.put("routine", routine)

        val memories = JSONArray()
        val date = SimpleDateFormat("dd.MM.yyyy", Locale("ru", "RU")).format(Date(time))
        memories.put(JSONObject().put("date", date).put("text", "Ты погладил Искру. Она обрадовалась и запомнила этот момент."))
        val previous = state.optJSONArray("memories")
        if (previous != null) {
            for (index in 0 until minOf(previous.length(), 39)) memories.put(previous.get(index))
        }
        state.put("memories", memories)

        val touches = state.optInt("overlayPetting", 0) + 1
        state.put("overlayPetting", touches)
        if (touches % 8 == 0) state.put("xp", (state.optInt("xp", 0) + 1).coerceAtMost(32))
        save.edit().putString("state_v1", state.toString()).apply()
    }

    @Suppress("DEPRECATION")
    private fun screenBounds(): Rect {
        val metrics = DisplayMetrics()
        windowManager.defaultDisplay.getRealMetrics(metrics)
        return Rect(0, 0, metrics.widthPixels, metrics.heightPixels)
    }

    private fun pauseForScreenOff() {
        screenOn = false
        handler.removeCallbacks(wander)
        if (::petView.isInitialized) petView.setAnimationEnabled(false)
    }

    private fun resumeForScreenOn() {
        screenOn = true
        if (::petView.isInitialized) petView.setAnimationEnabled(true)
        handler.removeCallbacks(wander)
        handler.post(wander)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Лисица поверх экрана", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Показывается, пока включён плавающий питомец"
            }
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val stopIntent = Intent(this, PetOverlayService::class.java).setAction(ACTION_STOP)
        val stopPending = PendingIntent.getService(this, 41, stopIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val openPending = PendingIntent.getActivity(this, 42, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, CHANNEL_ID) else Notification.Builder(this)
        return builder.setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentTitle("Лисица рядом")
            .setContentText("Нажми на лисицу, чтобы погладить; удерживай, чтобы открыть игру")
            .setContentIntent(openPending)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Выключить", stopPending).build())
            .build()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        if (receiverRegistered) runCatching { unregisterReceiver(screenReceiver) }
        if (::petView.isInitialized) runCatching { windowManager.removeView(petView) }
        save.edit().putBoolean("overlay_enabled", false).apply()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_STOP = "ru.livingpet.app.STOP_OVERLAY"
        private const val CHANNEL_ID = "living_pet_overlay"
        private const val NOTIFICATION_ID = 41
    }
}
