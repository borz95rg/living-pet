package ru.livingpet.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader

class MainActivity : Activity() {
    private lateinit var web: WebView
    private var waitingForOverlayPermission = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(22, 39, 48)
        window.navigationBarColor = android.graphics.Color.rgb(22, 39, 48)
        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        // Assets are served from https://appassets.androidplatform.net so that
        // three.js can fetch the GLB models (blocked for file:// URLs).
        web.settings.allowFileAccess = false
        web.settings.allowContentAccess = false
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        web.addJavascriptInterface(PetSaveBridge(this), "PetSave")
        web.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)
        }
        web.webChromeClient = WebChromeClient()
        setContentView(web)
        web.loadUrl("https://appassets.androidplatform.net/assets/index.html")
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7)
        }
    }

    override fun onResume() {
        super.onResume()
        web.onResume()
        if (waitingForOverlayPermission) {
            waitingForOverlayPermission = false
            if (Settings.canDrawOverlays(this)) startOverlay()
            else notifyOverlay(false)
        }
    }

    override fun onPause() {
        web.onPause()
        super.onPause()
    }

    fun startOverlay() {
        val intent = Intent(this, PetOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
        notifyOverlay(true)
    }

    fun stopOverlay() {
        startService(Intent(this, PetOverlayService::class.java).setAction(PetOverlayService.ACTION_STOP))
        notifyOverlay(false)
    }

    fun requestOverlayPermission() {
        waitingForOverlayPermission = true
        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
    }

    private fun notifyOverlay(enabled: Boolean) {
        web.post { web.evaluateJavascript("window.overlayStateChanged && window.overlayStateChanged($enabled)", null) }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}

/** Versioned game save kept in app-private Android preferences, outside the web cache. */
class PetSaveBridge(private val activity: MainActivity) {
    private val prefs = activity.getSharedPreferences("living_pet_save", Context.MODE_PRIVATE)
    private val main = Handler(Looper.getMainLooper())

    @JavascriptInterface
    fun load(): String = prefs.getString("state_v1", "") ?: ""

    @JavascriptInterface
    fun save(json: String) {
        if (json.length <= 200_000) prefs.edit().putString("state_v1", json).apply()
    }

    @JavascriptInterface
    fun overlayEnabled(): Boolean = prefs.getBoolean("overlay_enabled", false)

    @JavascriptInterface
    fun enableOverlay() {
        main.post {
            if (Settings.canDrawOverlays(activity)) activity.startOverlay()
            else activity.requestOverlayPermission()
        }
    }

    @JavascriptInterface
    fun disableOverlay() {
        main.post { activity.stopOverlay() }
    }
}
