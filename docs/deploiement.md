# Déploiement

| Composant | Hébergeur | URL |
|---|---|---|
| Frontend | Vercel | https://p14-dev-ia-olive.vercel.app |
| API | Railway | https://p14devia-production-67a4.up.railway.app |
| Base de données | PostgreSQL sur Railway, dans le même projet que l'API | interne |

Les deux plateformes redéploient automatiquement à chaque push sur `main`.

## Frontend sur Vercel

1. Importer le dépôt GitHub dans Vercel.
2. **Root Directory** : `frontend`. Le framework (Next.js) est détecté.
3. Variable d'environnement `NEXT_PUBLIC_API_URL` = URL publique de l'API (sans slash final), de type
   « Config » et non « Secret » : elle est exposée au navigateur par nature. Elle est figée au build :
   après un changement, redéployer le frontend.
4. Node 22 est imposé par le champ `engines` de `frontend/package.json`.

## Backend sur Railway

1. Créer un projet Railway depuis le dépôt GitHub, puis ajouter un service **PostgreSQL** dans le
   même projet.
2. Service de l'API : **Root Directory** `/backend`. Railway construit l'image avec
   `backend/Dockerfile`, dont les chemins sont relatifs à `backend/` (le squelette d'origine
   supposait la racine du dépôt, d'où une correction documentée dans [`decisions.md`](decisions.md)).
3. **Networking** : générer un domaine public pour l'API.
4. **Settings → Deploy → Wait for CI** : activé. Railway ne déploie `main` qu'une fois la CI GitHub
   verte.
5. Renseigner les variables ci-dessous. Aucune valeur n'est écrite dans le dépôt.

### Variables du service API

| Variable | Valeur attendue |
|---|---|
| `DATABASE_URL` | Référence `${{Postgres.DATABASE_URL}}` (jamais copiée à la main) |
| `JWT_SECRET` | Chaîne aléatoire d'au moins 32 caractères, **distincte de celle du développement** (`openssl rand -hex 32`) |
| `JWT_EXPIRE_MINUTES` | Durée de validité des tokens (ex. `60`) |
| `LLM_MODEL` | `anthropic:claude-haiku-5-5` (surtout pas `test`) |
| `ANTHROPIC_API_KEY` | Clé Anthropic **dédiée à la production** |
| `WORLDNEWS_API_KEY` | Clé WorldNewsAPI |
| `FRONTEND_ORIGINS` | URL du frontend, sans slash final (`https://p14-dev-ia-olive.vercel.app`) |
| `NEWS_COUNTRY` | Pays des actualités du jour (ex. `fr`) |
| `NEWS_LANGUAGE` | Langue des actualités du jour (ex. `fr`) |
| `TOP_NEWS_CACHE_TTL_SECONDS` | Cache des actualités du jour (ex. `3600`) |
| `TOP_NEWS_FAILURE_TTL_SECONDS` | Délai avant de retenter après un échec (ex. `300`) |
| `SQL_ECHO` | `false` |
| `PORT` | Fournie par Railway, ne pas la fixer |

Le descriptif complet de chaque variable est dans [`developpement.md`](developpement.md).
`MLFLOW_TRACKING_URI` n'est **jamais** posée en production.

### Vérifier un déploiement

```bash
API=https://p14devia-production-67a4.up.railway.app

curl -s $API/                                           # {"message":"👋"}
curl -s -X POST $API/login -H 'Content-Type: application/json' \
  -d '{"email":"test@test.com","password":"test"}'      # renvoie un access_token
```

Puis, depuis le frontend : connexion, nouvelle discussion, envoi d'un message, génération d'une revue.
Une erreur CORS dans la console du navigateur indique un `FRONTEND_ORIGINS` incorrect.

## Redéployer

Le backend n'est pas en ligne en permanence : une production inutilisée coûte de l'argent et expose
une clé pour rien. Le redéploiement part du dépôt (Dockerfile, CI, variables ci-dessus) et est
reproductible. Calendrier prévu :

- **Maintenant** : validation de l'application pendant l'essai Railway de 30 jours.
- **Fin de l'essai** : suppression du projet Railway et révocation de la clé `newsfoundry-prod`.
- **2 à 3 semaines avant la soutenance (juillet 2027)** : redéploiement, selon les étapes suivantes.

### Pas à pas

1. **Plan Railway** : passer le compte en plan **Hobby** pour un mois (avant juillet 2027).
2. **Nouvelle clé Anthropic de production** : dans la console Anthropic, créer une clé dédiée
   (`newsfoundry-prod`). Ne pas réutiliser une clé révoquée ni la clé de développement.
3. **Nouveau projet Railway** : le créer depuis le dépôt, ajouter PostgreSQL, définir le Root
   Directory `/backend`, générer le domaine public, activer « Wait for CI ».
4. **Variables** : saisir celles du tableau ci-dessus, avec un nouveau `JWT_SECRET`.
5. **Redeploy** : lancer un « Redeploy » du service API une fois les variables enregistrées.
6. **Frontend** : si le domaine public de l'API a changé, mettre à jour `NEXT_PUBLIC_API_URL` sur
   Vercel puis **redéployer** le frontend (la valeur est figée au build). Reporter la nouvelle URL
   dans ce document et dans le `README.md`.
7. **Vérifier** : suivre « Vérifier un déploiement » ci-dessus. Les tables et le compte de test sont
   recréés au démarrage de l'API.
8. **Après la soutenance** : supprimer le projet Railway, puis révoquer la clé
   `newsfoundry-prod` dans la console Anthropic.

> Les clés Anthropic du projet sont valides jusqu'au 31/07/2027 à 12 h : à prolonger si la
> soutenance a lieu plus tard.

## Secrets

- Aucun secret n'est commité : `.env` est ignoré, `.env.example` ne contient aucune valeur.
- La clé Anthropic de production est distincte de celle du développement, et le `JWT_SECRET` de
  production diffère du local : une clé peut être révoquée sans toucher à l'autre environnement, et
  les coûts de chacun se suivent séparément.
- La clé WorldNewsAPI est partagée entre local et production (plan gratuit, aucun coût) : leur quota
  de 50 points par jour est donc commun.
