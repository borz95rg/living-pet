package ru.livingpet.app

import android.app.Activity
import android.Manifest
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.JavascriptInterface
import android.webkit.WebViewClient
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.os.Build
import android.webkit.WebView
import android.content.pm.PackageManager

class MainActivity : Activity() {
    private var petWeb: WebView? = null
    private var overlayPermissionRequested = false
    private val notificationPermissionRequest = 5103
    @Suppress("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(22, 39, 48)
        window.navigationBarColor = android.graphics.Color.rgb(22, 39, 48)
        val web = WebView(this)
        petWeb = web
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = true
        web.settings.allowContentAccess = false
        web.addJavascriptInterface(PetSaveBridge(this, { enableOverlay() }, { disableOverlay() }), "PetSave")
        web.webViewClient = WebViewClient()
        web.webChromeClient = WebChromeClient()
        setContentView(web)
        web.loadUrl("file:///android_asset/index.html")
    }

    private fun enableOverlay() {
        runOnUiThread {
            if (Settings.canDrawOverlays(this)) {
                startPetOverlay()
            } else {
                overlayPermissionRequested = true
                startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            }
        }
    }

    private fun startPetOverlay() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), notificationPermissionRequest)
            return
        }
        val service = Intent(this, PetOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(service) else startService(service)
        petWeb?.post { petWeb?.evaluateJavascript("window.overlayStateChanged && window.overlayStateChanged(true)", null) }
    }

    private fun disableOverlay() {
        runOnUiThread {
            stopService(Intent(this, PetOverlayService::class.java))
            petWeb?.post { petWeb?.evaluateJavascript("window.overlayStateChanged && window.overlayStateChanged(false)", null) }
        }
    }

    override fun onResume() {
        super.onResume()
        if (overlayPermissionRequested) {
            overlayPermissionRequested = false
            if (Settings.canDrawOverlays(this)) enableOverlay()
            petWeb?.post { petWeb?.evaluateJavascript("window.overlayStateChanged && window.overlayStateChanged(${Settings.canDrawOverlays(this)})", null) }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == notificationPermissionRequest) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED && Settings.canDrawOverlays(this)) {
                startPetOverlay()
            } else {
                petWeb?.post { petWeb?.evaluateJavascript("window.overlayStateChanged && window.overlayStateChanged(false)", null) }
            }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val web = (window.decorView.findViewById(android.R.id.content) as? android.view.ViewGroup)
            ?.getChildAt(0) as? WebView
        if (web?.canGoBack() == true) web.goBack() else super.onBackPressed()
    }
}

/** Versioned game save kept in app-private Android preferences, outside the web cache. */
class PetSaveBridge(context: Context, private val requestOverlay: () -> Unit, private val stopOverlay: () -> Unit) {
    private val prefs = context.getSharedPreferences("living_pet_save", Context.MODE_PRIVATE)

    @JavascriptInterface
    fun load(): String = prefs.getString("state_v1", "") ?: ""

    @JavascriptInterface
    fun save(json: String) {
        if (json.length <= 200_000) prefs.edit().putString("state_v1", json).apply()
    }

    @JavascriptInterface
    fun enableOverlay() = requestOverlay()

    @JavascriptInterface
    fun disableOverlay() = stopOverlay()

    @JavascriptInterface
    fun overlayEnabled(): Boolean = prefs.getBoolean("overlay_enabled", false)
}
