package ru.livingpet.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.Shader
import android.view.View
import android.os.SystemClock
import kotlin.math.PI
import kotlin.math.sin

/**
 * Animated vector prototype. Replace this View with a glTF/Filament renderer
 * when the Blender GLB exports have been generated and validated.
 */
class FoxPetView(context: Context, private val growthStage: Int = 0) : View(context) {
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val orange = Color.rgb(238, 105, 30)
    private val orangeLight = Color.rgb(255, 153, 67)
    private val cream = Color.rgb(255, 225, 190)
    private val dark = Color.rgb(55, 30, 25)
    private val pink = Color.rgb(235, 125, 130)
    private var mood = "idle"
    private var moodUntil = 0L
    private var lastTap = 0L
    var faceRight = true
    private var lookX = 0f
    private var blinkAt = SystemClock.uptimeMillis() + 2400
    private var blinkUntil = 0L
    private var stepStart = SystemClock.uptimeMillis()
    private var animationEnabled = true
    private var walking = false
    private var contentScale = 1f
    private var contentLeft = 0f
    private var contentTop = 0f

    init { setLayerType(View.LAYER_TYPE_SOFTWARE, null) }

    fun reactTo(part: String) {
        val now = SystemClock.uptimeMillis()
        mood = when (part) {
            "head" -> "happy"
            "ear" -> "ear"
            "tail" -> "tail"
            else -> "surprised"
        }
        moodUntil = now + 1800
        lastTap = now
        invalidate()
    }

    fun onDragged(dx: Int) {
        faceRight = dx >= 0
        mood = "curious"
        moodUntil = SystemClock.uptimeMillis() + 700
        invalidate()
    }

    fun setWalking(value: Boolean) {
        walking = value
        invalidate()
    }

    fun setAnimationEnabled(value: Boolean) {
        animationEnabled = value
        if (value) invalidate()
    }

    fun reactAt(viewX: Float, viewY: Float) {
        val x = (viewX - contentLeft) / contentScale
        val y = (viewY - contentTop) / contentScale
        val part = when {
            y < 105f && (x < 105f || x > 165f) -> "ear"
            y < 150f -> "head"
            x < 82f && y > 105f -> "tail"
            else -> "body"
        }
        reactTo(part)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val baseScale = minOf(width / 260f, height / 250f)
        val growthScale = when (growthStage.coerceIn(0, 4)) {
            0 -> .70f
            1 -> .79f
            2 -> .88f
            3 -> .96f
            else -> 1f
        }
        contentScale = baseScale * growthScale
        contentLeft = (width - 260f * contentScale) / 2f
        contentTop = (height - 250f * contentScale) / 2f
        canvas.save()
        canvas.translate(contentLeft, contentTop)
        canvas.scale(contentScale, contentScale)
        val now = SystemClock.uptimeMillis()
        val t = now / 1000f
        if (now > moodUntil) mood = "idle"
        if (now >= blinkAt) {
            blinkUntil = now + 130
            blinkAt = now + 2300 + (now % 1900)
        }
        val blinking = now < blinkUntil
        val bob = sin(t * 2.2f) * 2.2f
        val wag = sin(t * 8.0f) * 0.22f
        val direction = if (faceRight) 1f else -1f

        canvas.save()
        canvas.scale(direction, 1f, 130f, 125f)
        canvas.translate(0f, bob)

        if (growthStage >= 4) {
            p.shader = RadialGradient(130f, 125f, 118f, intArrayOf(0x88FFD66E.toInt(), 0x00FFD66E), null, Shader.TileMode.CLAMP)
            canvas.drawCircle(130f, 125f, 118f, p)
            p.shader = null
        }

        // Soft ground shadow
        p.color = 0x55301810
        canvas.drawOval(45f, 207f, 220f, 235f, p)

        // Fluffy tail: three overlapping lobes with animated sway.
        canvas.save()
        canvas.rotate((sin(t * 5f) * 13f + if (mood == "tail") 28f else 0f), 94f, 151f)
        p.color = orange
        canvas.drawOval(25f, 107f, 125f, 205f, p)
        p.color = orangeLight
        canvas.drawOval(28f, 113f, 116f, 194f, p)
        p.color = cream
        canvas.drawOval(25f, 105f, 72f, 153f, p)
        canvas.restore()

        // Body and chest
        p.color = orange
        canvas.drawOval(72f, 128f, 193f, 214f, p)
        p.color = cream
        canvas.drawOval(104f, 146f, 175f, 211f, p)

        // Legs, with simple alternating gait when the pet has recently been dragged.
        val gait = if (walking || now - lastTap < 1000) sin(t * 13f) * 7f else sin(t * 2f) * 1.5f
        drawLeg(canvas, 96f, 184f, gait, orange)
        drawLeg(canvas, 159f, 184f, -gait, orange)
        drawLeg(canvas, 119f, 190f, -gait, orangeLight)
        drawLeg(canvas, 177f, 190f, gait, orangeLight)

        // Head
        p.color = orange
        canvas.drawCircle(135f, 104f, 61f, p)
        p.color = cream
        canvas.drawOval(91f, 113f, 178f, 166f, p)

        // Ears
        drawEar(canvas, 91f, 64f, -1f, t)
        drawEar(canvas, 166f, 64f, 1f, t)

        // Eyes, pupils follow a tiny horizontal gaze offset; blink closes them.
        val eyeH = if (blinking) 3f else 17f
        val pupilOffset = if (mood == "curious") 5f else 1.5f
        p.color = Color.WHITE
        canvas.drawOval(105f, 91f, 129f, 91f + eyeH, p)
        canvas.drawOval(143f, 91f, 167f, 91f + eyeH, p)
        if (!blinking) {
            p.color = dark
            canvas.drawCircle(119f + pupilOffset, 100f, 8f, p)
            canvas.drawCircle(155f + pupilOffset, 100f, 8f, p)
            p.color = Color.WHITE
            canvas.drawCircle(121f + pupilOffset, 96f, 2.8f, p)
            canvas.drawCircle(157f + pupilOffset, 96f, 2.8f, p)
        } else {
            p.color = dark
            p.strokeWidth = 3.5f
            canvas.drawLine(106f, 101f, 128f, 101f, p)
            canvas.drawLine(144f, 101f, 166f, 101f, p)
        }

        // Muzzle, nose and mouth
        p.color = cream
        canvas.drawOval(119f, 119f, 157f, 147f, p)
        p.color = dark
        canvas.drawCircle(138f, 126f, 5.5f, p)
        p.style = Paint.Style.STROKE
        p.strokeWidth = 2.4f
        val mouth = Path().apply {
            moveTo(138f, 131f); quadTo(130f, 142f, 123f, 135f)
            moveTo(138f, 131f); quadTo(146f, 142f, 153f, 135f)
        }
        canvas.drawPath(mouth, p)
        p.style = Paint.Style.FILL

        // Cheek blush
        p.color = 0x66F08080
        canvas.drawCircle(101f, 126f, 9f, p)
        canvas.drawCircle(174f, 126f, 9f, p)

        // Small floating reaction symbol
        if (now < moodUntil) {
            p.color = when (mood) { "happy" -> Color.rgb(255, 100, 145); "surprised" -> Color.YELLOW; else -> Color.WHITE }
            p.textSize = 25f
            canvas.drawText(if (mood == "happy") "♥" else if (mood == "surprised") "!" else "✦", 184f, 56f, p)
        }

        canvas.restore()
        canvas.restore()
        if (animationEnabled) postInvalidateDelayed(50)
    }

    private fun drawLeg(c: Canvas, x: Float, y: Float, angle: Float, color: Int) {
        c.save()
        c.rotate(angle, x, y)
        p.color = color
        c.drawRoundRect(x - 10f, y - 4f, x + 10f, y + 34f, 9f, 9f, p)
        p.color = dark
        c.drawOval(x - 12f, y + 25f, x + 13f, y + 39f, p)
        c.restore()
    }

    private fun drawEar(c: Canvas, x: Float, y: Float, side: Float, t: Float) {
        c.save()
        val twitch = if (mood == "ear") sin(t * 25f) * 10f else sin(t * 2f + side) * 2f
        c.rotate(side * twitch, x, y + 20f)
        val path = Path().apply {
            moveTo(x - 23f, y + 19f)
            quadTo(x - 24f, y - 36f, x + 1f, y - 42f)
            quadTo(x + 28f, y - 15f, x + 22f, y + 20f)
            close()
        }
        p.color = orange
        c.drawPath(path, p)
        val inner = Path().apply {
            moveTo(x - 12f, y + 9f)
            quadTo(x - 12f, y - 19f, x + 1f, y - 28f)
            quadTo(x + 15f, y - 8f, x + 12f, y + 10f)
            close()
        }
        p.color = pink
        c.drawPath(inner, p)
        c.restore()
    }
}
