package ru.livingpet.app

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.webkit.WebViewAssetLoader

/**
 * Floating 3D fox. Renders assets/overlay.html (three.js + fur shader + GLB models)
 * in a transparent WebView. The Canvas fox (FoxPetView) stays as a fallback when
 * WebGL is unavailable or the model fails to load.
 *
 * Public API is unchanged from the previous SceneView version, so PetOverlayService
 * keeps working: setWalking, setSleeping, playAction, reactAt, onDragged, faceRight…
 */
@SuppressLint("SetJavaScriptEnabled", "ViewConstructor")
class FoxPet3DView(
    context: Context,
    private val growthStage: Int,
    startSleeping: Boolean = false
) : FrameLayout(context) {
    private val fallback = FoxPetView(context, growthStage)
    private val web = WebView(context)
    private val main = Handler(Looper.getMainLooper())
    private var touchHandler: ((MotionEvent) -> Boolean)? = null
    private var ready = false
    private var failed = false
    private val pending = ArrayList<String>()

    var faceRight: Boolean = true
        set(value) {
            field = value
            fallback.faceRight = value
            js("Overlay.face(${if (value) 1 else -1})")
        }

    init {
        clipChildren = false
        val lp = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT)
        fallback.layoutParams = lp
        web.layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT)
        web.setBackgroundColor(Color.TRANSPARENT)
        web.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        web.isVerticalScrollBarEnabled = false
        web.isHorizontalScrollBarEnabled = false
        web.settings.javaScriptEnabled = true
        web.settings.allowFileAccess = false
        web.settings.allowContentAccess = false
        web.settings.mediaPlaybackRequiresUserGesture = true
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(context))
            .build()
        web.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)
        }
        web.addJavascriptInterface(Bridge(), "OverlayBridge")
        fallback.visibility = View.VISIBLE
        web.alpha = 0f
        addView(fallback)
        addView(web)
        val stage = growthStage.coerceIn(0, 4)
        web.loadUrl("https://appassets.androidplatform.net/assets/overlay.html?stage=$stage&sleep=${if (startSleeping) 1 else 0}")
        // If WebGL never answers, keep the Canvas fox.
        main.postDelayed({ if (!ready) showFallback() }, 12_000L)
    }

    private inner class Bridge {
        @JavascriptInterface
        fun ready() = main.post {
            if (failed) return@post
            ready = true
            fallback.visibility = View.GONE
            web.animate().alpha(1f).setDuration(250).start()
            pending.forEach { web.evaluateJavascript(it, null) }
            pending.clear()
        }

        @JavascriptInterface
        fun failed(@Suppress("UNUSED_PARAMETER") reason: String) = main.post { showFallback() }
    }

    private fun showFallback() {
        failed = true
        ready = false
        web.visibility = View.GONE
        fallback.visibility = View.VISIBLE
    }

    private fun js(code: String) {
        if (failed) return
        if (ready) web.evaluateJavascript(code, null) else pending.add(code)
    }

    /** All touches go to the service (drag / tap / long press), never to the WebView. */
    override fun onInterceptTouchEvent(ev: MotionEvent): Boolean = true

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN || event.actionMasked == MotionEvent.ACTION_MOVE) {
            js("Overlay.look(${event.x}, ${event.y})")
        }
        return touchHandler?.invoke(event) ?: false
    }

    fun setTouchHandler(handler: (MotionEvent) -> Boolean) {
        touchHandler = handler
    }

    fun setWalking(value: Boolean, running: Boolean = false) {
        fallback.setWalking(value)
        js("Overlay.walk($value, $running)")
    }

    fun setSleeping(value: Boolean) {
        fallback.setWalking(false)
        js("Overlay.sleep($value)")
    }

    /** One-shot clip: React, Jump, Stretch. Run/Walk are handled by setWalking. */
    fun playAction(clip: String, @Suppress("UNUSED_PARAMETER") durationMs: Long) {
        when (clip) {
            "Run" -> js("Overlay.walk(true, true)")
            "Walk" -> js("Overlay.walk(true, false)")
            else -> js("Overlay.action('${clip.filter { it.isLetter() }}')")
        }
    }

    fun setAnimationEnabled(value: Boolean) {
        fallback.setAnimationEnabled(value)
        js("Overlay.pause(${!value})")
        if (value) web.onResume() else web.onPause()
    }

    fun onDragged(dx: Int) {
        fallback.onDragged(dx)
        js("Overlay.drag($dx)")
    }

    /** Per-move window displacement in px: tail and ears swing with inertia. */
    fun nudge(dx: Int, dy: Int) {
        if (dx != 0 || dy != 0) js("Overlay.nudge($dx, $dy)")
    }

    fun dragEnd() = js("Overlay.dragEnd()")

    fun reactAt(viewX: Float, viewY: Float) {
        fallback.reactAt(viewX, viewY)
        js("Overlay.react($viewX, $viewY)")
    }

    fun destroy() {
        main.removeCallbacksAndMessages(null)
        web.removeJavascriptInterface("OverlayBridge")
        web.destroy()
    }
}
