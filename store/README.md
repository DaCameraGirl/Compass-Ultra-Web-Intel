# Store Packaging

Compass Ultra Web Intel should ship to stores as a hosted web product wrapped for each platform, not as a local Python/Streamlit process.

## App Identity

- Product name: Compass Ultra Web Intel
- Bundle ID / package name: `com.compassultra.webintel`
- Category: Business / Developer Tools
- Primary URL: set with `COMPASS_WEB_INTEL_URL`

## Required Before Submission

- Production hosted app URL with HTTPS
- App icon set: 1024x1024 source plus platform-generated sizes
- Screenshots for each store
- Privacy policy URL
- Terms URL
- Apple Developer account
- Google Play Console account
- Microsoft Partner Center account
- Platform signing certificates

## Platform Paths

- Google Play: Capacitor Android wrapper in `store/capacitor`
- Apple App Store: Capacitor iOS wrapper in `store/capacitor`
- Microsoft Store: PWA/MSIX packaging notes in `store/microsoft`

The wrappers should point at the hosted app. Keep Snowflake, Anthropic, Stripe, and other secrets on the server side only.

