import { defineConfig, fontProviders } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://blog.innjw.com',
  integrations: [mdx(), sitemap()],
  i18n: {
    defaultLocale: 'ko',
    locales: ['ko'],
  },
  fonts: [
    {
      provider: fontProviders.google(),
      name: 'Pretendard',
      cssVariable: '--font-pretendard',
      weights: [400, 500, 600, 700],
    },
  ],
});
