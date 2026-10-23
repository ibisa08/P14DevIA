import { Bot, User } from "lucide-react";
import type { ReactNode } from "react";

import { Markdown } from "@/components/Markdown";
import { formatTime } from "@/lib/format";

type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
  /** Absent tant que le message n'est pas enregistré côté serveur */
  createdAt?: string;
  /** Contenu affiché sous la bulle (ex. statut d'envoi) */
  footer?: ReactNode;
};

/** Bulle de message : journaliste sombre à droite, assistant clair à gauche (maquette). */
export function MessageBubble({ role, content, createdAt, footer }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <li className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <span
        aria-hidden="true"
        className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-zinc-950 text-white" : "bg-zinc-100 text-zinc-700"
        }`}
      >
        {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
      </span>

      <div className={`flex max-w-[85%] flex-col sm:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-lg px-4 py-3 ${
            isUser ? "bg-zinc-800 text-white" : "bg-zinc-100 text-zinc-900"
          }`}
        >
          {/* Locuteur annoncé aux lecteurs d'écran, la position et la couleur étant visuelles */}
          <span className="sr-only">{isUser ? "Vous : " : "Assistant : "}</span>
          {isUser ? (
            <p className="break-words whitespace-pre-wrap">{content}</p>
          ) : (
            <div className="break-words">
              <Markdown>{content}</Markdown>
            </div>
          )}
          {createdAt && (
            <time
              dateTime={createdAt}
              className={`mt-3 block text-xs ${isUser ? "text-zinc-300" : "text-zinc-600"}`}
            >
              {formatTime(createdAt)}
            </time>
          )}
        </div>
        {footer}
      </div>
    </li>
  );
}
