# Google Play Release Readiness & Compliance Guide

**Application ID:** `com.vybe.travel`  
**Application Name:** VYBE: Travel Marketplace  
**Platform Version:** Android 15 (Target SDK 35, Compile SDK 35, Min SDK 26)  
**Publishing Format:** Android App Bundle (`.aab`)  
**Compliance Standard:** Google Play Policy (2026 Edition)  

---

## 1. Store Listing Metadata & Copy

### 1.1 App Title (Max 30 characters)
```text
VYBE: Travel Marketplace
```

### 1.2 Short Description (Max 80 characters)
```text
Discover curated group trips, swipe packages & connect directly with operators.
```

### 1.3 Full Description (Max 4,000 characters)
```text
Explore the world your way with VYBE — the modern travel marketplace connecting adventurous travellers with verified, passionate tour operators.

Whether you're craving a high-altitude Himalayan trek, a coastal Mediterranean escape, or a remote cultural immersion, VYBE makes discovering, tailoring, and booking unforgettable trips seamless, transparent, and direct.

KEY FEATURES:

✨ DISCOVER & SWIPE PACKAGES
Browse immersive, image-rich travel itineraries tailored to your travel style and vibe. Swipe right on trips you love to instantly save them to your favourites or initiate direct enquiries.

🤝 DIRECT OPERATOR CONNECTION
No confusing intermediaries. Chat directly with the local travel companies running your trip. Ask questions, request custom itinerary tweaks, and receive bespoke quotations directly in the app.

⚡ RELIABLE BOOKING REQUESTS
Submit real-time booking requests with instant capacity reservation. View transparent price breakdowns and immutable terms snapshots so there are never any hidden fees or surprise price hikes.

🛡️ VERIFIED OPERATORS ONLY
Every tour operator on VYBE undergoes rigorous compliance checks, business document verification, and admin approval before listing packages. Travel with complete peace of mind.

💳 SECURE IN-APP PAYMENTS
When you're ready to confirm, pay securely using India's leading payment gateway (Razorpay), supporting UPI, net banking, debit cards, and credit cards with instant payment receipts.

🔔 REAL-TIME TRIP ALERTS
Receive instant in-app and push notification updates on booking request confirmations, operator quotations, itinerary changes, and departure countdowns.

PRIVACY & SAFETY:
Your privacy is our priority. We collect only the data needed to fulfill your bookings, enforce end-to-end HTTPS encryption, and provide both in-app and web-based account deletion at any time.

Download VYBE today and find your next adventure!
```

### 1.4 Categorization & Tags
- **Primary Category:** Travel & Local
- **Tags:** Travel, Vacation planning, Tour operators, Group travel, Adventure, Trip marketplace

---

## 2. Graphic Assets Specifications

| Asset | Dimensions | Format | Requirement |
| :--- | :--- | :--- | :--- |
| **App Icon** | 512 x 512 px | 32-bit PNG, max 1MB | Full bleed, no alpha transparent background |
| **Feature Graphic** | 1024 x 500 px | JPEG or 24-bit PNG, max 15MB | Cinematic brand visual (Amalfi / Spider Lily theme) |
| **Phone Screenshots** | Min 1080 x 1920 px (9:16) | JPEG or PNG (min 4, max 8) | Swipe deck, package details, chat, and booking flow |
| **7-Inch Tablet Screenshots**| Min 1200 x 1920 px | JPEG or PNG | Responsive tablet viewport layout |

---

## 3. Google Play Data Safety Questionnaire Declarations

Google Play requires accurate declarations of data collected, shared, and stored by the app and embedded SDKs.

### 3.1 Overview Summary
- **Data Encrypted in Transit:** **Yes** (All communication uses TLS 1.3/HTTPS).
- **Data Collection Required / Optional:** Required for core marketplace features (users can delete data at any time).
- **Account Deletion Provided:** **Yes** (In-app + web URL `https://vybe-travel-marketplace.onrender.com/account/delete-request`).

### 3.2 Data Type Declarations

| Data Category | Data Type | Collected? | Shared? | Purpose | Retention / Deletion |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Personal Info** | Name | Yes | No | Account management, Booking communication | Deleted/anonymized upon user request |
| | Email Address | Yes | No | Account authentication, Verification, Alerts | Deleted/anonymized upon user request |
| | User IDs | Yes | No | Internal database identification | Deleted/anonymized upon user request |
| **Financial Info** | Purchase History | Yes | No | Order confirmation, Taxation compliance | Anonymized; transaction records retained for statutory tax audits |
| | Credit/Debit Card Info | **No** | **No** | Processed directly by Razorpay (PCI-DSS compliant iframe) | Never touches VYBE servers |
| **Files & Documents** | Files/Docs | Yes | No | Operator verification documents (licenses/certificates) | Private Cloudflare R2 bucket; access restricted to Admins |
| **App Activity** | App Interactions | Yes | No | Package views, swipe saves, search queries | Internal analytics to improve recommendations |
| **Device or other IDs**| FCM Device Tokens | Yes | No | Push notification delivery | Revoked on logout or account deletion |

---

## 4. Account Deletion Compliance (Google Play Policy)

Google Play policy mandates that any app supporting account creation must provide:
1. **In-App Account Deletion:** Available inside the app under Profile settings (`POST /api/auth/delete-account`).
2. **Web-Accessible Deletion Request Portal:** Accessible without reinstalling the app at:  
   👉 `https://vybe-travel-marketplace.onrender.com/account/delete-request`

When account deletion is completed:
- The user's name and email are permanently anonymized (`deleted_UID_TIMESTAMP@anonymized.vybe`).
- Password hash is overwritten with an inaccessible string.
- Traveler profile and preference records are permanently purged.
- Device push notification tokens are deleted.
- Active authentication sessions are terminated.

---

## 5. Build, Signing & Release Instructions

### 5.1 Step 1: Create Production Release Keystore
Run in PowerShell / Terminal:
```powershell
keytool -genkeypair -v `
  -keystore vybe-release.keystore `
  -alias vybe-key `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000 `
  -storepass YOUR_SECURE_PASSWORD `
  -keypass YOUR_SECURE_PASSWORD `
  -dname "CN=VYBE Travel, OU=Mobile, O=VYBE, L=Mumbai, ST=Maharashtra, C=IN"
```
> [!IMPORTANT]
> Keep `vybe-release.keystore` and its passwords in a secure password manager. Never commit keystore files to Git.

### 5.2 Step 2: Configure Signing in `android/app/build.gradle`
```groovy
signingConfigs {
    release {
        storeFile file("path/to/vybe-release.keystore")
        storePassword System.getenv("KEYSTORE_PASSWORD")
        keyAlias "vybe-key"
        keyPassword System.getenv("KEY_PASSWORD")
    }
}
```

### 5.3 Step 3: Compile Signed Android App Bundle (AAB)
```bash
cd android
./gradlew bundleRelease
```
The output file `android/app/build/outputs/bundle/release/app-release.aab` is ready for direct upload to Google Play Console.

---

## 6. Pre-Submission Verification Checklist

- [x] **Target SDK 35 (Android 15)** configured in `android/app/build.gradle`.
- [x] **Min SDK 26 (Android 8.0)** supporting 96%+ of active Android devices.
- [x] **Cleartext Traffic Disabled**: `android:usesCleartextTraffic="false"` verified in `AndroidManifest.xml`.
- [x] **Permissions Audit**: Only `INTERNET`, `ACCESS_NETWORK_STATE`, and `POST_NOTIFICATIONS` declared.
- [x] **Hardware Back Navigation**: `OnBackPressedCallback` handles history without exiting app unexpectedly.
- [x] **Offline Protection**: `offline.html` displays with retry action when connection is lost.
- [x] **Adaptive Icons**: Defined for all DPI buckets in `res/mipmap-anydpi-v26/`.
- [x] **Privacy Policy Live**: Accessible at `https://vybe-travel-marketplace.onrender.com/privacy`.
- [x] **Public Account Deletion URL Live**: Accessible at `https://vybe-travel-marketplace.onrender.com/account/delete-request`.
- [x] **Data Safety Form Prepared**: Accurate declarations mapped to actual application data handling.
