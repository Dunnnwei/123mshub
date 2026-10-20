# Third-party notices

HAUI implementation is independently written. Palette color data and design specifications were studied from the MIT project [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), particularly `apps/shared/src/theme-presets.ts` and the desktop theme specifications. No upstream application code, commercial fonts, screenshots, logo or brand artwork is included. Public palette data is reproduced with its attribution; this is not an official product or endorsement. Reference snapshot inspected locally on 2026-10-18.

Palette provenance: GitHub and Nous derive from [GitHub VS Code Theme](https://github.com/primer/github-vscode-theme) (MIT); Catppuccin from [Catppuccin for VS Code](https://github.com/catppuccin/vscode) (MIT); Everforest from [sainnhe/everforest](https://github.com/sainnhe/everforest) (MIT); Solarized from [ryanolsonx/vscode-solarized-theme](https://github.com/ryanolsonx/vscode-solarized-theme) (MIT). Nous Alt and the remaining palette specifications are attributed to Nous Research (MIT). Classic is labeled neutrally in the product.

| Dependency | License | Source |
| --- | --- | --- |
| React / React DOM | MIT | https://github.com/facebook/react |
| Radix UI | MIT | https://github.com/radix-ui/primitives |
| class-variance-authority | Apache-2.0 | https://github.com/joe-bell/cva |
| clsx | MIT | https://github.com/lukeed/clsx |
| tailwind-merge | MIT | https://github.com/dcastil/tailwind-merge |
| cmdk | MIT | https://github.com/pacocoursey/cmdk |
| Motion | MIT | https://github.com/motiondivision/motion |
| Tabler Icons | MIT | https://github.com/tabler/tabler-icons |
| Culori | MIT | https://github.com/Evercoder/culori |
| Tailwind CSS | MIT | https://github.com/tailwindlabs/tailwindcss |
| JetBrains Mono | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono |
| Space Grotesk | SIL OFL 1.1 | https://github.com/floriankarsten/space-grotesk |

The two bundled Latin variable woff2 files are distributed through Fontsource; their full OFL files accompany them in `src/fonts` and the package's `dist/fonts`. Other scripts use system font fallback. Full dependency licenses and palette provenance licenses are retained in `licenses/` and copied into the distributable library. Runtime dependency versions are locked in `package-lock.json`.

Development tools: Vite (MIT), TypeScript (Apache-2.0), tsup (MIT), Vitest (MIT), Playwright (Apache-2.0), axe-core (MPL-2.0), Lighthouse (Apache-2.0), Fontsource (MIT distribution tooling; fonts retain OFL). These are development dependencies and are not bundled into the library runtime.

The original requirement documents may name excluded fonts and brands to identify constraints. They are not product source or runtime assets and are intentionally excluded from the product scan. This provenance notice is similarly excluded so legally required attribution is preserved.
