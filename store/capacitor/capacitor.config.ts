import type { CapacitorConfig } from '@capacitor/cli';

const hostedUrl = process.env.COMPASS_WEB_INTEL_URL;

const config: CapacitorConfig = {
  appId: 'com.compassultra.webintel',
  appName: 'Compass Ultra Web Intel',
  webDir: 'dist',
  bundledWebRuntime: false,
  ...(hostedUrl
    ? {
        server: {
          url: hostedUrl,
          cleartext: false,
        },
      }
    : {}),
};

export default config;

