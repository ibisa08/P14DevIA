import { clearToken, getToken } from "@/lib/auth";

// Valeur figée au build par Next.js (variable NEXT_PUBLIC_*) ; slash final retiré
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export const ERROR_MESSAGES = {
  invalidCredentials: "Email ou mot de passe incorrect.",
  sessionExpired: "Ta session a expiré. Reconnecte-toi.",
  unavailable: "Le service est momentanément indisponible. Réessaie dans quelques instants.",
  server: "Une erreur est survenue côté serveur.",
  invalidRequest: "La requête est invalide.",
  unexpected: "Une erreur inattendue est survenue.",
  storageUnavailable:
    "Impossible d'enregistrer la session : vérifie que le stockage du navigateur est autorisé.",
  assistantFailed: "L'assistant n'a pas pu répondre, réessaie.",
} as const;

/** Erreur d'API avec un message déjà prêt à afficher à l'utilisateur. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    // 0 = le serveur n'a pas répondu (éteint, réseau coupé, CORS refusé)
    this.status = status;
  }
}

export type User = { id: number; email: string };
type TokenResponse = { access_token: string; token_type: string };

// Les dates sont des chaînes ISO 8601 avec fuseau (UTC), à formater côté client
export type ChatSummary = { id: number; title: string; created_at: string; updated_at: string };
export type ChatMessage = { role: "user" | "assistant"; content: string; created_at: string };
export type Chat = ChatSummary & { messages: ChatMessage[] };

export type ReviewArticle = {
  title: string;
  summary: string;
  source: string | null;
  url: string | null;
};
export type PressReview = {
  id: number;
  chat_id: number;
  topic: string;
  title: string;
  content: { title: string; summary: string; articles: ReviewArticle[] };
  created_at: string;
};

/** Longueur maximale d'un message, alignée sur l'API (MESSAGE_MAX_LENGTH). */
export const MESSAGE_MAX_LENGTH = 4000;
/** Longueur maximale du sujet d'une revue, alignée sur l'API (TOPIC_MAX_LENGTH). */
export const TOPIC_MAX_LENGTH = 200;

type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  /** Joindre le token (défaut). À désactiver pour /login. */
  auth?: boolean;
};

export async function apiRequest<T>(
  path: string,
  { body, auth = true, headers, ...init }: ApiRequestOptions = {},
): Promise<T> {
  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");
  if (body !== undefined) requestHeaders.set("Content-Type", "application/json");
  const token = auth ? getToken() : null;
  if (token) requestHeaders.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // fetch ne rejette que si aucune réponse HTTP n'a été reçue
    throw new ApiError(0, ERROR_MESSAGES.unavailable);
  }

  if (response.ok) {
    return (response.status === 204 ? undefined : await response.json()) as T;
  }

  const detail = await readDetail(response);

  // Token absent, expiré ou révoqué : on repart d'une session propre
  if (response.status === 401 && auth) {
    clearToken();
    if (window.location.pathname !== "/login") window.location.replace("/login");
  }

  throw new ApiError(response.status, toUserMessage(response.status, auth, detail));
}

/** Lit le champ `detail` du format d'erreur de l'API ({"detail": "..."}). */
async function readDetail(response: Response): Promise<string | null> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    // Corps vide ou non JSON (ex. page d'erreur d'un proxy)
  }
  return null;
}

function toUserMessage(status: number, authenticated: boolean, detail: string | null): string {
  if (status === 401) {
    return authenticated ? ERROR_MESSAGES.sessionExpired : ERROR_MESSAGES.invalidCredentials;
  }
  // Le backend renvoie déjà une phrase lisible pour les erreurs de validation
  if (status === 422) return detail ?? ERROR_MESSAGES.invalidRequest;
  // 502 = le modèle n'a pas répondu : erreur temporaire, l'utilisateur peut réessayer
  if (status === 502) return ERROR_MESSAGES.assistantFailed;
  if (status >= 500) return ERROR_MESSAGES.server;
  return detail ?? ERROR_MESSAGES.unexpected;
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/login", {
    method: "POST",
    body: { email, password },
    auth: false,
  });
}

export function getMe(): Promise<User> {
  return apiRequest<User>("/me");
}

export function listChats(): Promise<ChatSummary[]> {
  return apiRequest<ChatSummary[]>("/chats");
}

export function createChat(): Promise<Chat> {
  return apiRequest<Chat>("/chats", { method: "POST" });
}

export function getChat(chatId: number): Promise<Chat> {
  return apiRequest<Chat>(`/chats/${chatId}`);
}

/** Envoie un message et renvoie la discussion complète, réponse de l'assistant comprise. */
export function sendMessage(chatId: number, content: string): Promise<Chat> {
  return apiRequest<Chat>(`/chats/${chatId}/messages`, { method: "POST", body: { content } });
}

export function generateReview(chatId: number, topic: string): Promise<PressReview> {
  return apiRequest<PressReview>(`/chats/${chatId}/reviews`, { method: "POST", body: { topic } });
}

export function listReviews(): Promise<PressReview[]> {
  return apiRequest<PressReview[]>("/reviews");
}
