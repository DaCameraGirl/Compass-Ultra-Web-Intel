# Microsoft Store Packaging

Use the hosted Compass Ultra Web Intel app as a PWA or wrap it as MSIX after the production URL is live.

## Recommended Route

1. Host the app over HTTPS.
2. Add `store/pwa/manifest.webmanifest` to the hosted web app.
3. Generate production icons from a 1024x1024 source asset.
4. Package with PWABuilder or Visual Studio MSIX tooling.
5. Submit through Microsoft Partner Center.

## Store Metadata

- Name: Compass Ultra Web Intel
- Package identity: `com.compassultra.webintel`
- Category: Developer tools or Business
- Website: `https://www.compassultra.com/`
- Privacy policy: `https://www.compassultra.com/privacy`
- Terms: `https://www.compassultra.com/terms`

