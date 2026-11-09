plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ru.livingpet.app"
    compileSdk = 35

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    defaultConfig {
        applicationId = "ru.livingpet.app"
        minSdk = 24
        targetSdk = 35
        versionCode = providers.gradleProperty("buildVersionCode").orNull?.toInt() ?: 1
        versionName = providers.gradleProperty("buildVersionName").orNull ?: "0.1.0"
    }

    val keystorePath = System.getenv("ANDROID_KEYSTORE_PATH")
    val storePasswordValue = System.getenv("ANDROID_KEYSTORE_PASSWORD")
    val aliasValue = System.getenv("ANDROID_KEY_ALIAS")
    val keyPasswordValue = System.getenv("ANDROID_KEY_PASSWORD")

    if (keystorePath != null && storePasswordValue != null && aliasValue != null && keyPasswordValue != null) {
        signingConfigs {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = storePasswordValue
                keyAlias = aliasValue
                keyPassword = keyPasswordValue
            }
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            if (keystorePath != null && storePasswordValue != null && aliasValue != null && keyPasswordValue != null) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
}

dependencies {
    // View-based Filament renderer for transparent GLB overlays.
    implementation("io.github.sceneview:sceneview:2.3.0")
    // SceneView's public API exposes these AndroidX and coroutine types.
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
