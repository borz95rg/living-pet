package ru.livingpet.app

import android.content.Context
import android.graphics.PixelFormat
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import io.github.sceneview.SceneView
import io.github.sceneview.node.ModelNode
import io.github.sceneview.math.Position

/** Transparent Filament view for the animated fox, with the Canvas pet as a load/error fallback. */
class FoxPet3DView(
    context: Context,
    private val growthStage: Int
) : FrameLayout(context), LifecycleOwner {
    override val lifecycle = LifecycleRegistry(this)
    private val fallback = FoxPetView(context, growthStage)
    private val scene = SceneView(context, isOpaque = false)
    private var modelNode: ModelNode? = null
    private var touchHandler: ((MotionEvent) -> Boolean)? = null
    private var animationEnabled = true
    private var walking = false
    private var sleeping = false
    private var actionTask: Runnable? = null
    var faceRight: Boolean = true
        set(value) {
            field = value
            fallback.faceRight = value
        }
    private var reactionTask: Runnable? = null

    init {
        lifecycle.currentState = Lifecycle.State.CREATED
        scene.lifecycle = lifecycle
        clipChildren = false
        clipToPadding = false
        fallback.layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT)
        scene.layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT)
        scene.holder.setFormat(PixelFormat.TRANSLUCENT)
        scene.setZOrderOnTop(true)
        scene.onTouchEvent = { event, _ -> touchHandler?.invoke(event) == true }
        addView(fallback)
        addView(scene)
        val stageName = listOf("baby", "cub", "teen", "adult", "legendary")[growthStage.coerceIn(0, 4)]
        scene.modelLoader.loadModelInstanceAsync("models/fox_stage_${growthStage + 1}_$stageName.glb") { instance ->
            post {
                if (instance == null) return@post
                runCatching {
                    val node = ModelNode(
                        modelInstance = instance,
                        autoAnimate = false,
                        scaleToUnits = 1.55f,
                        centerOrigin = Position(x = 0f, y = -1f, z = 0f)
                    )
                    scene.addChildNode(node)
                    modelNode = node
                    fallback.visibility = View.GONE
                    playBaseAnimation()
                }.onFailure {
                    // Keep the playable Canvas pet visible if a device cannot initialize Filament.
                    fallback.visibility = View.VISIBLE
                }
            }
        }
    }

    fun setTouchHandler(handler: (MotionEvent) -> Boolean) {
        touchHandler = handler
    }

    fun setWalking(value: Boolean) {
        walking = value
        fallback.setWalking(value)
        if (animationEnabled) playBaseAnimation()
    }

    fun setSleeping(value: Boolean) {
        sleeping = value
        walking = false
        fallback.setWalking(false)
        if (animationEnabled) playBaseAnimation()
    }

    /** Play a short authored action, then return to sleep, walk, or idle. */
    fun playAction(clip: String, durationMs: Long) {
        if (!animationEnabled || modelNode == null) return
        actionTask?.let { removeCallbacks(it) }
        playClip(clip, loop = false)
        val task = Runnable { playBaseAnimation() }
        actionTask = task
        postDelayed(task, durationMs)
    }

    fun setAnimationEnabled(value: Boolean) {
        animationEnabled = value
        fallback.setAnimationEnabled(value)
        if (isAttachedToWindow) {
            lifecycle.currentState = if (value) Lifecycle.State.RESUMED else Lifecycle.State.STARTED
        }
        if (value) playBaseAnimation()
        else stopCurrentClip()
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        lifecycle.currentState = if (animationEnabled) Lifecycle.State.RESUMED else Lifecycle.State.STARTED
    }

    override fun onDetachedFromWindow() {
        lifecycle.currentState = Lifecycle.State.DESTROYED
        super.onDetachedFromWindow()
    }

    fun onDragged(dx: Int) {
        fallback.onDragged(dx)
        playReaction()
    }

    fun reactAt(viewX: Float, viewY: Float) {
        fallback.reactAt(viewX, viewY)
        playReaction()
    }

    private fun clipName(clip: String) = "Fox_${listOf("Baby", "Cub", "Teen", "Adult", "Legendary")[growthStage.coerceIn(0, 4)]}_$clip"

    private fun playBaseAnimation() {
        playClip(when { sleeping -> "Sleep"; walking -> "Walk"; else -> "Idle" }, loop = true)
    }

    private var currentClip: String? = null

    private fun playClip(clip: String, loop: Boolean) {
        if (!animationEnabled) return
        val node = modelNode ?: return
        stopCurrentClip()
        currentClip = clipName(clip)
        node.playAnimation(currentClip!!, loop = loop)
    }

    private fun stopCurrentClip() {
        currentClip?.let { modelNode?.stopAnimation(it) }
        currentClip = null
        reactionTask?.let { removeCallbacks(it) }
        reactionTask = null
        actionTask?.let { removeCallbacks(it) }
        actionTask = null
    }

    private fun playReaction() {
        if (!animationEnabled || modelNode == null) return
        playClip("React", loop = false)
        val task = Runnable { playBaseAnimation() }
        reactionTask = task
        postDelayed(task, 1100L)
    }
}
