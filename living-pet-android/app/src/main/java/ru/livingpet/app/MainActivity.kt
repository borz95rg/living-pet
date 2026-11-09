package ru.livingpet.app

import android.app.Activity
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.content.Context

class MainActivity : Activity() {
    @Suppress("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(22, 39, 48)
        window.navigationBarColor = android.graphics.Color.rgb(22, 39, 48)
        val web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = true
        web.settings.allowContentAccess = false
        web.addJavascriptInterface(PetSaveBridge(this), "PetSave")
        web.webViewClient = WebViewClient()
        web.webChromeClient = WebChromeClient()
        setContentView(web)
        web.loadUrl("file:///android_asset/index.html")
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val web = (window.decorView.findViewById(android.R.id.content) as? android.view.ViewGroup)
            ?.getChildAt(0) as? WebView
        if (web?.canGoBack() == true) web.goBack() else super.onBackPressed()
    }
}

/** Versioned game save kept in app-private Android preferences, outside the web cache. */
class PetSaveBridge(context: Context) {
    private val prefs = context.getSharedPreferences("living_pet_save", Context.MODE_PRIVATE)

    @JavascriptInterface
    fun load(): String = prefs.getString("state_v1", "") ?: ""

    @JavascriptInterface
    fun save(json: String) {
        if (json.length <= 200_000) prefs.edit().putString("state_v1", json).apply()
    }
}
