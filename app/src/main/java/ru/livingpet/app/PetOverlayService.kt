package ru.livingpet.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import org.json.JSONObject

class PetOverlayService : Service() {
    private lateinit var windowManager: WindowManager
    private var petView: View? = null
    private lateinit var layout: WindowManager.LayoutParams
    private val channelId = "living_pet_overlay"

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        createNotificationChannel()
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
        startForeground(NOTIFICATION_ID, buildNotification())
        if (petView == null) showPet()
        getSharedPreferences("living_pet_save", MODE_PRIVATE).edit().putBoolean("overlay_enabled", true).apply()
        return START_NOT_STICKY
    }

    private fun showPet() {
        val state = getSharedPreferences("living_pet_save", MODE_PRIVATE).getString("state_v1", "")
        val kind = try { JSONObject(state ?: "{}").optString("kind", "fox") } catch (_: Exception) { "fox" }
        val animal = when (kind) { "wolf" -> "🐺"; "cat" -> "🐱"; "dog" -> "🐶"; else -> "🦊" }
        val density = resources.displayMetrics.density
        val avatar = TextView(this).apply {
            text = animal
            textSize = 34f
            gravity = Gravity.CENTER
            contentDescription = "Питомец. Перетащи меня или нажми, чтобы открыть игру"
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.argb(235, 255, 250, 240))
                setStroke((1.5f * density).toInt(), Color.argb(210, 143, 190, 163))
            }
            elevation = 8f * density
        }
        layout = WindowManager.LayoutParams(
            (68 * density).toInt(), (68 * density).toInt(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (12 * density).toInt()
            y = (resources.displayMetrics.heightPixels * .55f).toInt()
        }
        avatar.setOnTouchListener(DragTouchListener(avatar, density))
        petView = avatar
        try { windowManager.addView(avatar, layout) } catch (_: SecurityException) { stopSelf() }
    }

    private inner class DragTouchListener(private val view: View, private val density: Float) : View.OnTouchListener {
        private var downX = 0f
        private var downY = 0f
        private var startX = 0
        private var startY = 0
        private var dragged = false
        override fun onTouch(v: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX; downY = event.rawY
                    startX = layout.x; startY = layout.y; dragged = false
                    return true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX; val dy = event.rawY - downY
                    if (kotlin.math.abs(dx) + kotlin.math.abs(dy) > 8 * density) dragged = true
                    if (dragged) {
                        layout.x = (startX + dx).toInt(); layout.y = (startY + dy).toInt()
                        try { windowManager.updateViewLayout(view, layout) } catch (_: Exception) { }
                    }
                    return true
                }
                MotionEvent.ACTION_UP -> {
                    if (!dragged) {
                        val open = Intent(this@PetOverlayService, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                        startActivity(open)
                    }
                    return true
                }
            }
            return false
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "Питомец поверх экрана", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Показывается, пока включён плавающий питомец"
            }
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val stopIntent = Intent(this, PetOverlayService::class.java).setAction(ACTION_STOP)
        val stopPending = PendingIntent.getService(this, 1, stopIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val openIntent = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, channelId) else Notification.Builder(this)
        return builder.setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentTitle("Питомец рядом")
            .setContentText("Нажми на питомца, чтобы открыть игру")
            .setContentIntent(openIntent)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Выключить", stopPending).build())
            .build()
    }

    override fun onDestroy() {
        getSharedPreferences("living_pet_save", MODE_PRIVATE).edit().putBoolean("overlay_enabled", false).apply()
        petView?.let { try { windowManager.removeView(it) } catch (_: Exception) { } }
        petView = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val ACTION_STOP = "ru.livingpet.app.STOP_OVERLAY"
        private const val NOTIFICATION_ID = 41
    }
}
