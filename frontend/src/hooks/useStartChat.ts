"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useChats } from "@/components/ChatsProvider";
import { ApiError, ERROR_MESSAGES, createChat } from "@/lib/api";
import { setPendingMessage } from "@/lib/pendingMessages";

/**
 * Premier envoi depuis une page sans discussion (accueil, revues) : crée le chat, l'ajoute à
 * la sidebar puis ouvre sa page, qui envoie le message (voir lib/pendingMessages).
 */
export function useStartChat() {
  const router = useRouter();
  const { upsertChat } = useChats();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startChat(content: string): Promise<void> {
    setStarting(true);
    setError(null);
    try {
      const chat = await createChat();
      upsertChat(chat);
      setPendingMessage(chat.id, content);
      router.push(`/chats/${chat.id}`);
    } catch (err) {
      // Le texte reste dans la zone de saisie : rien n'est perdu
      setError(err instanceof ApiError ? err.message : ERROR_MESSAGES.unexpected);
      setStarting(false);
    }
  }

  return { startChat, starting, error };
}
