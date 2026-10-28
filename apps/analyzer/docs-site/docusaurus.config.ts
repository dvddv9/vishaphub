import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Vishap',
  tagline: 'Security analysis for engineering materials',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  url: 'https://dvddv9.github.io',
  baseUrl: '/vishap/',

  organizationName: 'dvddv9',
  projectName: 'vishap',

  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/dvddv9/vishap/tree/main/docs-site/',
        },
        blog: {
          showReadingTime: true,
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/docusaurus-social-card.jpg',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Vishap',
      logo: {
        alt: 'Vishap logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/blog',
          label: 'Blog',
          position: 'left',
        },
        {
          href: 'https://github.com/dvddv9/vishap',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Getting Started', to: '/docs/getting-started'},
            {label: 'API Reference', to: '/docs/api-reference'},
            {label: 'CLI', to: '/docs/cli'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'GitHub', href: 'https://github.com/dvddv9/vishap'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Vishap.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'java', 'c', 'bash', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
