# Décisions techniques

Chaque choix est suivi de sa raison. Les décisions sont regroupées par thème ; l'architecture est
décrite dans [`architecture.md`](architecture.md) et la procédure de mise en ligne dans
[`deploiement.md`](deploiement.md).

- [Authentification et sécurité](#authentification-et-sécurité)
- [API et données](#api-et-données)
- [Agents IA](#agents-ia)
- [WorldNewsAPI](#worldnewsapi)
- [Tests](#tests)
- [Déploiement](#déploiement)
- [Frontend](#frontend)
- [Écarts avec les maquettes](#écarts-avec-les-maquettes)

## Authentification et sécurité

- **`JWT_SECRET` obligatoire, 32 caractères minimum.** Pas de valeur par défaut : un secret oublié en
  production ferait signer les tokens avec une valeur connue. L'application refuse de démarrer avec un
  message lisible (`Configuration invalide (JWT_SECRET : Field required)`). 32 caractères = 256 bits,
  la taille recommandée pour HS256.
- **JWT HS256 avec liste blanche d'algorithmes.** `jwt.decode(..., algorithms=["HS256"])` bloque les
  attaques par changement d'algorithme (`alg: none`). Les claims `sub`, `iat` et `exp` sont exigés ;
  `sub` est une chaîne (RFC 7519 et PyJWT). Un token valide dont l'utilisateur a été supprimé donne 401.
- **Login sans fuite d'information, en temps constant.** Email inconnu et mauvais mot de passe
  renvoient le même 401 « Identifiants invalides ». Si l'utilisateur n'existe pas, le mot de passe est
  quand même vérifié contre un hash factice : le temps de réponse ne révèle pas l'existence d'un compte.
- **Isolation stricte : 404 filtré dans la requête SQL.** `WHERE id = :id AND user_id = :user` : le
  chat d'un autre utilisateur n'est jamais chargé en mémoire, et la réponse (404 « Discussion
  introuvable ») est identique à celle d'un id inexistant, pour ne pas révéler son existence. Testé avec
  deux utilisateurs sur toutes les routes, y compris la vérification que le modèle n'est jamais appelé.
- **CORS sans credentials.** L'authentification passe par le header `Authorization` (token en
  localStorage), pas par des cookies : `allow_credentials=False` réduit la surface d'attaque. Les
  origines autorisées viennent de `FRONTEND_ORIGINS`.
- **Compte de test public en production.** `test@test.com` / `test` est créé au démarrage, y compris
  en production : voulu pour l'évaluation, l'application n'ayant pas d'inscription. À supprimer dans un
  vrai produit.
- **Logs sans contenu de discussion ni secret.** `logging` plutôt que `print` (niveaux, nom du
  module). Le middleware d'erreurs ne journalise que la méthode et le chemin, jamais les headers (le
  token n'apparaît donc jamais). httpx journalise chaque URL appelée, or celles de `/search-news`
  contiennent la recherche du journaliste : son logger est limité aux avertissements, et le client
  WorldNewsAPI journalise lui-même l'endpoint, le coût et les erreurs (testé : ni la clé ni la recherche
  n'apparaissent).

## API et données

- **Schémas d'API séparés des tables.** `LoginRequest`, `TokenResponse`, `UserRead`… sont distincts des
  modèles SQLModel : `hashed_password` ne peut pas fuiter dans une réponse.
- **Format d'erreur unique `{"detail": "..."}`.** Le front n'a qu'un format à lire. Les 422 de FastAPI
  (liste d'objets) sont convertis en phrase lisible en français ; les erreurs non gérées renvoient un
  500 JSON générique, détail dans les logs uniquement. Le middleware d'erreurs est enregistré avant CORS
  pour que les 500 portent aussi les headers CORS (sinon le navigateur les masque derrière un échec
  CORS).
- **Dates en UTC avec fuseau explicite.** Colonnes `timestamp with time zone` ; les réponses portent
  toujours un décalage (`Z`), sinon le navigateur interpréterait la date en heure locale. Le titre
  « Discussion du JJ/MM/AAAA » est calculé en heure de Paris, fuseau des utilisateurs.
- **Historique PydanticAI complet en JSON, vue simplifiée pour le front.** `Chat.messages` stocke
  l'historique brut (`ModelMessagesTypeAdapter`), nécessaire pour reprendre une discussion à
  l'identique et rejouer les appels d'outils. L'API n'expose qu'une vue `{role, content, created_at}` :
  instructions, appels d'outils et métadonnées du fournisseur restent internes. Colonne `JSON`
  générique de SQLAlchemy : `json` sous Postgres, texte sous SQLite (tests).
- **Création des tables au démarrage, sans migrations.** `create_all` suffit pour ce périmètre mais
  n'ajoute pas de colonne à une table existante : la base locale a reçu un `ALTER TABLE` manuel pour
  `loaded_articles`, la base de production, créée après, n'est pas concernée. Alembic est proposé dans
  [`ameliorations.md`](ameliorations.md).
- **Connexion à la base libérée pendant les appels externes.** La transaction de lecture est terminée
  avant l'appel au LLM ou à WorldNewsAPI (plusieurs secondes) : la connexion retourne au pool au lieu de
  rester « idle in transaction » côté Postgres.

## Agents IA

- **Modèle lu dans `LLM_MODEL`, jamais à l'import.** Obligatoire, au format PydanticAI
  `fournisseur:modèle` (`anthropic:claude-haiku-5-5` en production) ou `test` (`TestModel`, réponses
  factices sans clé ni réseau, pour développer l'interface). Pas de valeur par défaut : un oubli en
  production ne doit pas basculer en silence sur le modèle factice. Les agents sont créés sans modèle
  et le reçoivent à chaque appel : importer l'app n'instancie aucun fournisseur, donc ni la CI ni les
  tests n'ont besoin d'`ANTHROPIC_API_KEY`. La bannière PydanticAI du premier appel est désactivée
  (`BANNER_ENABLED = False`) pour ne pas polluer les logs.
- **`LLM_MODEL=test` n'appelle aucun outil.** Par défaut, `TestModel` appelle tous les outils avec des
  arguments générés : en développement, chaque message aurait lancé une vraie recherche WorldNewsAPI et
  vidé le quota. L'agent de chat reçoit donc `TestModel(call_tools=[])` (testé). Les tests de l'outil
  utilisent `FunctionModel` pour piloter précisément les appels.
- **Prompt système figé par chat.** Copié dans `Chat.system_prompt` à la création et passé en
  `instructions` à chaque appel : modifier le prompt dans le code ne change pas les discussions
  existantes (testé).
- **Actualités du jour figées dans ce prompt.** À `POST /chats`, 8 sujets (un article par sujet,
  résumés tronqués à 300 caractères, environ 1 000 tokens) sont ajoutés avec la date du jour et la
  consigne de citer média et lien. Figé voulu : une discussion reprise plus tard garde le contexte de sa
  création, ce qui la rend reproductible et évite qu'une réponse contredise les précédentes ; pour
  l'actualité récente, l'agent dispose de `search_news`. 8 sujets × 300 caractères : compromis entre
  couverture et coût en tokens, répété à chaque message. Le contenu de presse est délimité par des
  balises et présenté comme une donnée, jamais une consigne (injection de prompt via un titre). Un échec
  de WorldNewsAPI n'empêche jamais la création de la discussion : il est journalisé.
- **Outil `search_news` : paramètres simples, échecs signalés au modèle.** `query` (3 à 100
  caractères), `language` (code ISO 639-1, optionnel), `max_results` (1 à 5), validés par PydanticAI.
  Clé absente, quota ou panne : `ToolFailed` renvoie au modèle un échec explicite sans l'inviter à
  réessayer ; il répond sans les résultats et prévient le journaliste. `ModelRetry` est réservé aux
  arguments invalides (le modèle peut reformuler) : sur une panne, il consommerait du quota en relances
  puis ferait échouer le message en 502. 3 recherches au maximum par message. Seule la réponse finale de
  chaque échange est affichée (une réponse qui appelle un outil est une étape intermédiaire).
- **`Chat.loaded_articles`.** URL et titre de chaque article renvoyé par `search_news`, cumulés sans
  doublon sur la discussion et sauvegardés avec la réponse (rien n'est sauvegardé si le modèle échoue).
  Ils permettent de retrouver les sources consultées et préparent une éventuelle recherche sémantique.
- **Erreur du modèle : 502, rien de sauvegardé.** Clé manquante, quota, panne ou sortie structurée
  invalide : le client reçoit 502 « L'assistant n'a pas pu répondre, réessaie. », le détail part dans les
  logs, et l'historique n'est modifié qu'après une réponse complète : le message peut être renvoyé.
- **Agent de revue de presse : transcription texte en entrée.** Ce second agent (sans outil,
  `output_type` Pydantic) reçoit le sujet et la discussion en texte (« Journaliste : … / Assistant : … »)
  plutôt que l'historique brut : un historique contenant des appels d'outils serait refusé par certains
  fournisseurs pour un agent qui n'en déclare aucun. Une discussion vide renvoie 400 (l'agent ne pourrait
  qu'inventer). Les URL d'articles autres que `http(s)` sont écartées, car le front en fait des liens
  (pas de `javascript:`).
- **Traçage MLflow facultatif, développement local seulement.** Actif uniquement si
  `MLFLOW_TRACKING_URI` est défini, avec MLflow en groupe de dépendances `observability` : absent de la
  CI et de l'image Docker. Une trace contient les messages complets, d'où l'interdiction de la pointer
  ailleurs qu'en local. Le traçage est un outil de mesure, jamais une condition de démarrage : sans
  MLflow ou sans serveur, l'application démarre avec un avertissement.

## WorldNewsAPI

- **Sorties simplifiées, clé dans le header.** `services/news_api.py` ne renvoie jamais la réponse
  brute : titre, résumé tronqué (300 caractères), URL, source et date. Texte intégral, images et auteurs
  n'arrivent pas jusqu'au modèle (tokens). L'API ne donne pas le nom du média : on affiche le domaine de
  l'URL (`lemonde.fr`). La clé passe par le header `x-api-key` (recommandation de la doc) et non par
  `?api-key=` : elle n'apparaît dans aucune URL ni aucun log. `httpx` passe des dépendances de dev aux
  dépendances de production.
- **Erreurs typées.** `MissingApiKeyError`, `QuotaExceededError` (402 et 429), `NewsApiTimeoutError`,
  `InvalidResponseError`, journalisées avec l'endpoint et le message uniquement. Les headers
  `X-API-Quota-Request` et `X-API-Quota-Left` sont journalisés : coût réel de chaque appel.
- **Clé optionnelle : mode dégradé.** Sans `WORLDNEWS_API_KEY`, aucun appel n'est tenté : les
  discussions sont créées avec le prompt de base et « actualités indisponibles », et la recherche répond
  au modèle qu'elle est indisponible. La clé est un `SecretStr` (jamais dans un `repr` ou un log) et
  `WORLDNEWS_API_KEY=` vide vaut absence de clé.
- **Plan gratuit : 50 points par jour, 1 requête par seconde, 1 simultanée.**
  - Requêtes sérialisées (verrou) et espacées d'au moins 1 s.
  - `/top-news` en cache mémoire d'1 h (`TOP_NEWS_CACHE_TTL_SECONDS`) avec `max-news-per-cluster=1`
    pour alléger la réponse ; deux créations simultanées ne font qu'un appel.
  - Cache négatif de 5 min (`TOP_NEWS_FAILURE_TTL_SECONDS`) après un échec (quota, panne, timeout) :
    chaque création de chat ne retente pas un appel voué à l'échec, qui consommerait du quota ou ferait
    attendre jusqu'au timeout. Sans clé, pas de cache : aucun appel n'est fait.
  - `/search-news` : 5 résultats maximum, 3 recherches maximum par message.
  - Timeout court (5 s) : mieux vaut un chat sans actualités qu'une longue attente.
  - Cache et limitation vivent en mémoire : valable pour un seul processus d'API (cas du déploiement
    actuel).
- **Réponse `/top-news` vide : un échec, pas un succès.** Le 05/11/2026, `/top-news` a répondu HTTP 200
  avec `"top_news": []` (quota débité). Le client gardait ce résultat vide en cache 1 h comme un
  succès : toutes les discussions créées pendant ce temps partaient sans actualités et le modèle devait
  chercher à chaque question (3 recherches au lieu d'une pendant le test). Désormais une réponse sans
  sujet exploitable lève `EmptyTopNewsError` et suit le cache négatif de 5 minutes, avec un
  avertissement donnant le nombre de sujets reçus et écartés.
- **Une seule clé pour le local et la production.** Les 50 points quotidiens sont donc un budget
  commun. Constaté le 05/11/2026 : un test en production vers 12 h 15 (1 `/top-news` et 2 recherches,
  3,1 points) a fait baisser le quota vu depuis le local de 43,8 à 39,65 sans appel local. Choix assumé :
  pas de seconde clé pour un projet de cette taille (plan gratuit, aucun coût), au prix d'une règle de
  conduite : les tests locaux restent sobres et les points consommés se lisent dans les logs
  `X-API-Quota-Left`.

### Coûts mesurés (test du 29/10/2026, plan gratuit)

Relevés dans les headers `X-API-Quota-Request` et `X-API-Quota-Left` :

| Action | Appels WorldNewsAPI | Points | Temps de réponse de l'API NewsFoundry |
|---|---|---|---|
| Création d'un chat, cache vide | 1 × `/top-news` | 1,0 | 0,36 s |
| Création d'un chat, cache chaud | aucun | 0 | 0,02 s |
| Message déclenchant la recherche | 2 × `/search-news` (5 résultats) | 2 × 1,05 | 10,2 s (contre 5,8 s sans outil) |
| Revue de presse | aucun | 0 | 4,2 s |

- `/top-news` coûte 1 point fixe, malgré une vingtaine de sujets renvoyés ; `/search-news` suit la
  règle de la doc : 1 point plus 0,01 par résultat.
- Le modèle (Claude Haiku) a lancé 2 recherches pour une seule question, sous la limite de 3.
- Test complet (2 chats, 1 question, 1 revue) : 3,1 points, il en restait 46,9 sur 50.
- Budget quotidien : au pire 24 points pour `/top-news` (cache d'1 h, usage continu), soit environ
  12 messages avec 2 recherches sur le reste du quota.

## Tests

- **SQLite en mémoire (`StaticPool`).** Les tests ne touchent jamais la base de développement et la CI
  n'a pas besoin de service Postgres. Chaque test reçoit une base neuve ; `get_engine` et `get_session`
  sont des dépendances FastAPI surchargées dans `conftest.py`. `StaticPool` garde une seule connexion,
  sans quoi chaque connexion SQLite en mémoire verrait une base vide.
- **Aucun appel externe.** WorldNewsAPI est simulée par `httpx.MockTransport` (client injecté via une
  dépendance FastAPI, horloge contrôlée pour le cache et la limitation de débit). `conftest.py` force
  `LLM_MODEL=test`, retire `ANTHROPIC_API_KEY` et force `WORLDNEWS_API_KEY` à vide (une variable
  d'environnement prime sur le `.env`) : même avec de vraies clés dans le shell ou le `.env`, aucun test
  n'appelle Anthropic ni WorldNewsAPI.

## Déploiement

- **Dockerfile corrigé pour le Root Directory `backend/`.** Le squelette faisait `COPY backend/...`, ce
  qui suppose un contexte de build à la racine du dépôt, alors que Railway construit depuis `backend/`.
  Les `COPY` sont relatifs à `backend/`.
- **`.dockerignore`.** Exclut `.env` (secrets), `.venv/`, les caches Python et les tests : image plus
  légère et aucun secret local embarqué.
- **Image slim sans dépendances de dev : 1,61 Go → 352 Mo.** Base
  `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`, `uv sync --frozen --no-dev` (versions exactes du
  lockfile, sans pytest), lancement par `uv run --no-sync`.
- **« Wait for CI » sur Railway.** `main` n'est redéployé qu'une fois la CI verte : un commit qui casse
  les tests n'arrive pas en production.
- **`NEXT_PUBLIC_API_URL` en variable Config, pas Secret.** Elle est exposée au navigateur par nature :
  la masquer n'apporterait rien.
- **Postgres relié par référence.** `${{Postgres.DATABASE_URL}}` : l'URL n'est jamais copiée à la main.
- **Secrets de production distincts de ceux du développement.** Clé Anthropic dédiée
  (`newsfoundry-prod`) et `JWT_SECRET` différent du local : l'incident de sécurité Railway d'octobre
  2026 (vol de clés d'API d'IA) impose de pouvoir révoquer une clé sans toucher au développement, et une
  clé par environnement permet de suivre les coûts de chacun. Aucun secret n'est commité.
- **Pas de production permanente.** Elle coûte de l'argent et expose une clé pour rien pendant les mois
  sans usage, alors qu'un redéploiement à partir du dépôt est reproductible (Dockerfile, CI, variables
  listées dans `backend/.env.example`). Le calendrier jusqu'à la soutenance et la procédure sont dans
  [`deploiement.md`](deploiement.md#redéployer).
- **Vérifié en production :** CORS, login, `/me`, `/chats`, discussion, recherche d'actualités,
  génération d'une revue de presse.

## Frontend

- **`cacheComponents` désactivé.** L'application est une SPA client dont les données viennent de
  FastAPI avec un token en localStorage : le cache de composants serveur de Next.js 16 n'apporte rien.
  L'option `partialPrefetching`, qui en dépend, a donc été retirée.
- **`AGENTS.md` supprimé.** Fichier généré par create-next-app, sans utilité ici ; `agentRules: false`
  dans `next.config.ts` empêche `next dev` de le recréer (option vérifiée dans la doc Next 16.4).
- **Layout authentifié : groupe de routes `(app)`.** `/`, `/chats/[id]` et `/revues` partagent un
  layout (garde d'authentification, sidebar) sans effet sur les URL. La liste des discussions est
  chargée une fois dans un contexte React et mise à jour localement après création ou envoi.
- **Gardes de route avec `useSyncExternalStore`.** Le token est lu depuis localStorage : `undefined`
  tant qu'il n'est pas lu (rendu serveur, hydratation), puis `string | null`. Les gardes affichent un
  loader tant que la valeur est `undefined` : aucun flash de contenu protégé, et la connexion ou
  déconnexion dans un autre onglet est prise en compte.
- **Stockage du token protégé.** `localStorage` peut lever une exception (navigation privée stricte,
  stockage bloqué) : lecture et écriture sont protégées, et la page de connexion affiche un message
  explicite si la session ne peut pas être enregistrée.
- **Premier message envoyé par la page de la discussion.** Sur l'accueil, le premier envoi crée le chat
  puis navigue vers `/chats/[id]`, qui envoie le message : un seul code gère l'affichage immédiat,
  l'indicateur « L'assistant rédige… » et les erreurs. Le message transite par une Map en mémoire, lue
  au rendu et consommée une seule fois dans un effet (pas de double envoi en mode strict de React).
- **Le texte saisi n'est jamais perdu.** En cas d'échec (502, réseau), le message reste affiché « Non
  envoyé » avec « Réessayer », et revient dans la zone de saisie si elle est vide. Une erreur à la
  création d'une discussion laisse le texte dans la saisie.
- **Markdown sans HTML brut.** `react-markdown` et `remark-gfm` (listes, tableaux) pour les réponses de
  l'assistant ; `skipHtml` ignore tout HTML et les URL dangereuses (`javascript:`) sont neutralisées. Les
  titres Markdown sont rendus en gras pour ne pas casser la hiérarchie des titres de la page.
- **Accessibilité.** Bordures, placeholders et violet choisis pour respecter les ratios WCAG AA (4,5:1
  pour le texte, 3:1 pour les composants) ; focus clavier toujours visible (contour violet global). Fil
  de discussion en `role="log"` (nouveaux messages annoncés poliment), locuteur annoncé aux lecteurs
  d'écran (« Vous : », « Assistant : »), modale `<dialog>` native (focus piégé, Échap, retour du focus au
  bouton), confirmation de copie en `aria-live`, sidebar mobile invisible (et non seulement décalée)
  quand elle est fermée, pour ne pas être atteinte au clavier.
- **`npm audit` : vulnérabilités en dépendances de dev uniquement.** 5 vulnérabilités « high », toutes
  dans l'outillage de dev (`npm audit --omit=dev` : 0). Elles ne sont pas embarquées dans le bundle
  servi ; pas de `npm audit fix --force`, qui imposerait des montées de version cassantes.

## Écarts avec les maquettes

- **Connexion : champ mot de passe ajouté.** `POST /login` exige email et mot de passe, la maquette n'en
  montrait pas.
- **Connexion : bordure visible sur les champs.** Sans elle, le contraste champ/fond est sous le ratio
  3:1 exigé par le WCAG pour les composants d'interface.
- **En-tête de discussion : titre du chat** (« Discussion du JJ/MM/AAAA ») plutôt que « Nouvelle
  discussion », qui serait faux pour une discussion reprise.
- **Sidebar : heure ajoutée sous la date.** Sinon plusieurs discussions du même jour auraient des liens
  indiscernables (critère WCAG 2.4.4, objet des liens).
- **Revues : sujet demandé affiché sous la date.**
- **Revues : la zone de saisie** (présente sur la maquette) démarre une nouvelle discussion.
