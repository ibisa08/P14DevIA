# NewsFoundry Frontend

Application [Next.js](https://nextjs.org) (App Router, TypeScript, Tailwind), Node.js 22.19.

```bash
npm install
npm run dev      # http://localhost:3000 (l'API doit tourner sur NEXT_PUBLIC_API_URL)
npm run lint
npm run build
```

`NEXT_PUBLIC_API_URL` (défaut `http://localhost:8000`) est figée au build.

- Installation et variables : [`../docs/developpement.md`](../docs/developpement.md)
- Arborescence du frontend : [`../docs/architecture.md`](../docs/architecture.md)
- Déploiement sur Vercel : [`../docs/deploiement.md`](../docs/deploiement.md)
- Choix techniques (accessibilité, gestion du token, Markdown…) : [`../docs/decisions.md`](../docs/decisions.md)
