# clawchat-pet frontend

The complete React + TypeScript source for the web UI bundled with the plugin.

## Development

The local pet API must be available at `127.0.0.1:54321`.

```bash
npm ci
npm run dev
```

Vite runs at `127.0.0.1:5173` and proxies the pet API routes to port `54321`.

## Production build

```bash
npm ci
npm run build
```

The build output is written to `../clawchat_pet/web/`. Those generated files are committed so an installed plugin works without Node.js or a separate frontend build step.
