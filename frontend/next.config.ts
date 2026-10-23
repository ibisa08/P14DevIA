import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // App 100 % client (JWT en localStorage, données servies par FastAPI) : le cache serveur
  // de Cache Components n'apporte rien et impose des contraintes de rendu.
  // partialPrefetching exige cacheComponents, il est donc retiré aussi.
  cacheComponents: false,
  // Empêche `next dev` de (re)générer AGENTS.md
  agentRules: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
