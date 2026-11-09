# Исправление сборки Living Pet

- Исправлен `app/src/main/res/drawable/splash_screen.xml`: `android:gravity="centerCrop"` заменён на допустимое для BitmapDrawable значение `fill`. Это устраняет ошибку AAPT из GitHub Actions №18.
- XML заставки проверен на корректность разбора.
- Проверены контейнеры пяти GLB-моделей: GLB 2.0, длина заголовка совпадает с размером файла.

Сборка APK в этой среде не выполнялась: Android SDK и Gradle не установлены. После загрузки архива в GitHub запустите Actions → Build Android APK → Run workflow.
