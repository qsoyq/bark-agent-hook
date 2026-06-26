# OpenClaw plugin entry strategy

`index.js` is the only maintained OpenClaw plugin entry for this package.

The package intentionally points both `openclaw.extensions` and `openclaw.runtimeExtensions` at `./index.js`. OpenClaw requires `extensions` in `package.json` and prefers `runtimeExtensions` when loading installed packages so npm packages can avoid runtime TypeScript compilation. Keeping both fields on the same JavaScript file avoids a TypeScript build chain and removes the previous hand-maintained `index.ts` / `index.js` duplicate.

Validate the active entry with:

```bash
node --check plugins/bark-agent-hook-openclaw/index.js
```
