"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, ERROR_MESSAGES, listChats, type ChatSummary } from "@/lib/api";

type ChatsContextValue = {
  /** null = chargement en cours (ou en erreur) */
  chats: ChatSummary[] | null;
  error: string | null;
  reload: () => void;
  /** Ajoute ou met à jour une discussion après création ou envoi, sans recharger la liste. */
  upsertChat: (chat: ChatSummary) => void;
};

const ChatsContext = createContext<ChatsContextValue | null>(null);

// Même ordre que l'API : dernière activité d'abord
function byLastActivity(a: ChatSummary, b: ChatSummary): number {
  // Date.parse plutôt qu'une comparaison de chaînes : les microsecondes sont omises quand nulles
  return Date.parse(b.updated_at) - Date.parse(a.updated_at) || b.id - a.id;
}

/** Liste des discussions partagée entre la sidebar et les pages (une seule requête). */
export function ChatsProvider({ children }: { children: ReactNode }) {
  const [chats, setChats] = useState<ChatSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Incrémenté par reload() pour relancer le chargement
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listChats()
      .then((result) => {
        if (!cancelled) setChats(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : ERROR_MESSAGES.unexpected);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reload = useCallback(() => {
    setError(null);
    setChats(null);
    setAttempt((value) => value + 1);
  }, []);

  const upsertChat = useCallback(({ id, title, created_at, updated_at }: ChatSummary) => {
    // On ne garde que le résumé : l'objet reçu peut être une discussion complète avec messages
    const summary = { id, title, created_at, updated_at };
    setChats((current) =>
      current ? [...current.filter((chat) => chat.id !== id), summary].sort(byLastActivity) : current,
    );
  }, []);

  const value = useMemo(
    () => ({ chats, error, reload, upsertChat }),
    [chats, error, reload, upsertChat],
  );
  return <ChatsContext value={value}>{children}</ChatsContext>;
}

export function useChats(): ChatsContextValue {
  const context = useContext(ChatsContext);
  if (!context) throw new Error("useChats doit être utilisé sous <ChatsProvider>");
  return context;
}
