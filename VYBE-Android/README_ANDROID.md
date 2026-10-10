# VYBE Android app

Native Kotlin + Jetpack Compose + Material 3 client for the laptop-hosted
VYBE Flask backend. Sunset Coral + Deep Ocean theme. See `PARITY_CHECKLIST.md`
for feature coverage and `API_ANDROID.md` for backend usage.

## Prerequisites (Windows)

- **Android Studio** (any recent version; project targets the bundled JDK 17+).
  Confirm: Help → About shows a 2024.x+ build.
- **Android SDK**: platform `android-36` + build-tools `36.0.0` via
  Tools → SDK Manager → SDK Platforms / SDK Tools. (Already present on the
  dev laptop: `%LOCALAPPDATA%\Android\Sdk`.)
- **JDK**: Studio's bundled JBR works (Gradle JVM 17+). No separate install needed.
- **Backend running**: VYBE `run.bat` on the laptop (`http://127.0.0.1:5000`).
- No Gradle install needed (wrapper; first sync downloads Gradle 8.11.1).

## Open & run

1. Android Studio → Open → select the `VYBE-Android` folder → Trust project.
2. Let Gradle sync finish (downloads AGP 8.7.3, Kotlin 2.0.21, Compose BOM, Retrofit…).
3. Run ▶ on a Pixel emulator (API 30+) or USB-connected phone.
4. On the app login screen → **Server settings**:
   - Emulator: `http://10.0.2.2:5000` (default — do NOT use 127.0.0.1, that is the emulator itself).
   - Physical phone, same Wi-Fi: `http://<laptop-LAN-ip>:5000` (run.bat prints it).
   - Anywhere: paste the active ngrok `https://…` URL.
5. Log in with a demo account (`traveler@vybe.demo / traveler123`).

## Debug vs release networking

- Debug builds allow cleartext HTTP to the laptop (`src/debug` network config).
- Release builds allow HTTPS only. Never ship a debug build; never add
  cleartext exceptions for production hosts.

## Build APK (after a successful Studio sync)

```bat
cd VYBE-Android
gradlew.bat assembleDebug
```

APK: `app\build\outputs\apk\debug\app-debug.apk`. Install:
`adb install -r app\build\outputs\apk\debug\app-debug.apk`.

## Tests

- JVM unit tests: `./gradlew testDebugUnitTest` (pure-logic: prefs gating rules).
- Backend contract: the Flask suite (`pytest -q` in repo root, 43 pass) guards
  every endpoint this app consumes — run it after backend changes.

## Status (honest)

- Implemented + wired: auth, session restore, server config, Explore, detail,
  Discover (prefs gate, ranked deck, swipe gestures + buttons, like/save, edit prefs), Saved.
- NOT yet built: My Trips, Chats, Profile, operator tools, admin tools, Packing,
  AI Guide (see parity checklist). Backend endpoints for all of them already exist.
- **Not compiled here**: this environment has no Gradle distribution; open in
  Android Studio and sync before trusting the build. No APK produced yet.
- **Not tested end-to-end**: phone + laptop run is still manual (checklist §E2).
