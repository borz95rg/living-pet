plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ru.livingpet.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "ru.livingpet.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
}
