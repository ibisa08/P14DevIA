// Premier message saisi sur l'accueil, transmis à la page de la discussion qui vient d'être
// créée : c'est elle qui l'envoie, avec l'affichage immédiat, l'indicateur de rédaction et la
// gestion d'erreur (« Réessayer ») déjà en place pour les messages suivants.
// Simple Map en mémoire : elle survit à la navigation côté client, pas à un rechargement.
const pendingMessages = new Map<number, string>();

export function setPendingMessage(chatId: number, content: string): void {
  pendingMessages.set(chatId, content);
}

/** Lit le message en attente sans le consommer (lecture répétable, sûre pendant le rendu). */
export function peekPendingMessage(chatId: number): string | undefined {
  return pendingMessages.get(chatId);
}

/** Renvoie le message en attente (une seule fois) puis l'oublie. */
export function takePendingMessage(chatId: number): string | undefined {
  const content = pendingMessages.get(chatId);
  pendingMessages.delete(chatId);
  return content;
}
