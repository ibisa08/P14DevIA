import { useSyncExternalStore } from "react";

const TOKEN_KEY = "newsfoundry_token";
// Événement interne : l'événement natif « storage » ne se déclenche que dans les AUTRES onglets
const AUTH_CHANGE_EVENT = "newsfoundry:auth-change";

const isBrowser = () => typeof window !== "undefined";

export function getToken(): string | null {
  if (!isBrowser()) return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    // localStorage peut être bloqué (navigation privée stricte, cookies désactivés)
    return null;
  }
}

/** Enregistre le token ; renvoie false si le stockage du navigateur est indisponible. */
export function setToken(token: string): boolean {
  if (!isBrowser()) return false;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Stockage bloqué ou quota dépassé : l'appelant affiche un message à l'utilisateur
    return false;
  }
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
  return true;
}

export function clearToken(): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Stockage indisponible : aucun token n'a pu y être enregistré, rien à effacer
  }
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(AUTH_CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(AUTH_CHANGE_EVENT, onChange);
  };
}

/**
 * Token courant, réactif (connexion/déconnexion, y compris depuis un autre onglet).
 *
 * `undefined` = pas encore lu : rendu serveur et hydratation, où localStorage n'existe pas.
 * Les gardes de route attendent donc une valeur `string | null` avant de décider quoi afficher,
 * ce qui évite tout flash du contenu protégé.
 */
export function useAuthToken(): string | null | undefined {
  return useSyncExternalStore(subscribe, getToken, () => undefined);
}
