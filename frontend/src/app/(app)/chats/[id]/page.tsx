"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useChats } from "@/components/ChatsProvider";
import { Composer } from "@/components/Composer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { GenerateReviewButton } from "@/components/GenerateReviewButton";
import { MessageBubble } from "@/components/MessageBubble";
import { PageLoader } from "@/components/PageLoader";
import { ApiError, ERROR_MESSAGES, getChat, sendMessage, type Chat } from "@/lib/api";
import { peekPendingMessage, takePendingMessage } from "@/lib/pendingMessages";

/** Message affiché avant la réponse du serveur, ou resté en échec. */
type PendingMessage = { content: string; status: "sending" | "failed"; error?: string };
type LoadError = { status: number; message: string };

export default function ChatPage() {
  const { id } = useParams<{ id: string }>();
  const chatId = Number(id);

  if (!Number.isInteger(chatId) || chatId <= 0) return <ChatNotFound />;
  // key : changer de discussion repart d'un état vierge (messages, saisie, erreurs)
  return <ChatView key={chatId} chatId={chatId} />;
}

// Garde la version la plus récente : le chargement initial peut répondre après un envoi
function mostRecent(current: Chat | null, next: Chat): Chat {
  if (current && Date.parse(current.updated_at) > Date.parse(next.updated_at)) return current;
  return next;
}

function toErrorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : ERROR_MESSAGES.unexpected;
}

function ChatView({ chatId }: { chatId: number }) {
  const { upsertChat } = useChats();
  const [chat, setChat] = useState<Chat | null>(null);
  const [loadError, setLoadError] = useState<LoadError | null>(null);
  // Premier message saisi sur l'accueil : affiché « en cours d'envoi » dès le premier rendu
  const [pending, setPending] = useState<PendingMessage | null>(() => {
    const firstMessage = peekPendingMessage(chatId);
    return firstMessage ? { content: firstMessage, status: "sending" } : null;
  });
  const [draft, setDraft] = useState("");
  // Incrémenté par « Réessayer » pour relancer le chargement
  const [attempt, setAttempt] = useState(0);
  const threadRef = useRef<HTMLElement>(null);

  const sending = pending?.status === "sending";

  useEffect(() => {
    let cancelled = false;
    getChat(chatId)
      .then((result) => {
        if (!cancelled) setChat((current) => mostRecent(current, result));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError({ status: err instanceof ApiError ? err.status : 0, message: toErrorMessage(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chatId, attempt]);

  /** Envoie le message ; l'état « en cours d'envoi » doit déjà être affiché. */
  // Callbacks de promesse (et non async/await) : les mises à jour d'état ont lieu à la
  // réponse du serveur, ce qui permet d'appeler deliver() depuis un effet.
  function deliver(content: string): Promise<void> {
    return sendMessage(chatId, content).then(
      (updated) => {
        setChat((current) => mostRecent(current, updated));
        setPending(null);
        upsertChat(updated);
      },
      (err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setLoadError({ status: 404, message: err.message });
          return;
        }
        setPending({ content, status: "failed", error: toErrorMessage(err) });
        // Le texte n'est jamais perdu : il revient dans la saisie si elle est restée vide
        setDraft((currentDraft) => currentDraft || content);
      },
    );
  }

  function send(content: string) {
    setPending({ content, status: "sending" });
    void deliver(content);
  }

  // Premier message saisi sur l'accueil : envoyé dès l'ouverture de la discussion.
  // takePendingMessage ne le renvoie qu'une fois : pas de double envoi si l'effet est rejoué
  // (mode strict de React en développement).
  useEffect(() => {
    const firstMessage = takePendingMessage(chatId);
    if (firstMessage) void deliver(firstMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uniquement à l'ouverture du chat
  }, [chatId]);

  function handleSubmit(content: string) {
    setDraft("");
    send(content);
  }

  function retry() {
    if (!pending) return;
    // Évite un doublon si le texte avait été remis dans la saisie
    setDraft((currentDraft) => (currentDraft.trim() === pending.content ? "" : currentDraft));
    send(pending.content);
  }

  // Défilement automatique vers le dernier message ou l'indicateur de rédaction
  const messageCount = chat?.messages.length ?? 0;
  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    thread.scrollTo({ top: thread.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  }, [messageCount, pending]);

  if (loadError?.status === 404) return <ChatNotFound />;

  const messages = chat?.messages ?? [];

  return (
    <>
      <header className="flex h-[88px] shrink-0 items-center justify-between gap-3 border-b border-zinc-200 bg-zinc-50 px-4 sm:px-5">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <Link href="/" className="rounded-md p-1.5 text-zinc-800 hover:bg-zinc-200">
            <ArrowLeft aria-hidden="true" className="size-5" strokeWidth={1.5} />
            <span className="sr-only">Retour à l&apos;accueil</span>
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-zinc-900">{chat?.title ?? "Discussion"}</h1>
            <p className="text-sm text-zinc-600">Conversation active</p>
          </div>
        </div>
        <GenerateReviewButton chatId={chatId} disabled={messages.length === 0 || sending} />
      </header>

      <main ref={threadRef} className="min-h-0 flex-1 overflow-y-auto bg-canvas px-4 py-8 sm:px-8">
        {loadError ? (
          <div role="alert" className="mx-auto max-w-xl">
            <ErrorNotice
              action={
                <button
                  type="button"
                  onClick={() => {
                    setLoadError(null);
                    setAttempt((value) => value + 1);
                  }}
                  className="font-medium underline underline-offset-2"
                >
                  Réessayer
                </button>
              }
            >
              {loadError.message}
            </ErrorNotice>
          </div>
        ) : !chat && !pending ? (
          <div className="flex justify-center">
            <PageLoader label="Chargement de la discussion…" />
          </div>
        ) : (
          <div className="mx-auto max-w-5xl">
            {/* role="log" : les nouveaux messages sont annoncés sans interrompre la lecture */}
            <ol role="log" aria-live="polite" aria-label="Messages de la discussion" className="space-y-8">
              {messages.map((message, index) => (
                <MessageBubble
                  key={`${message.created_at}-${index}`}
                  role={message.role}
                  content={message.content}
                  createdAt={message.created_at}
                />
              ))}
              {pending && (
                <MessageBubble
                  role="user"
                  content={pending.content}
                  footer={
                    pending.status === "failed" && (
                      <p className="mt-1 text-xs font-medium text-red-800">Non envoyé</p>
                    )
                  }
                />
              )}
              {sending && <TypingIndicator />}
            </ol>

            {pending?.status === "failed" && (
              <div role="alert" className="mt-6">
                <ErrorNotice
                  action={
                    <button type="button" onClick={retry} className="font-medium underline underline-offset-2">
                      Réessayer
                    </button>
                  }
                >
                  {pending.error}
                </ErrorNotice>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Pas d'envoi tant que la discussion n'est pas chargée : le message serait invisible */}
      <Composer value={draft} onChange={setDraft} onSubmit={handleSubmit} busy={sending} disabled={!chat} />
    </>
  );
}

function TypingIndicator() {
  return (
    <li className="flex items-start gap-3">
      <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-zinc-100">
        <span className="size-2 animate-pulse rounded-full bg-violet-600 motion-reduce:animate-none" />
      </span>
      <p className="rounded-lg bg-zinc-100 px-4 py-3 text-sm text-zinc-700 italic">L&apos;assistant rédige…</p>
    </li>
  );
}

function ChatNotFound() {
  return (
    <main className="flex min-h-0 flex-1 items-center justify-center bg-canvas px-4 py-8">
      <div className="max-w-md rounded-xl bg-white px-6 py-10 text-center">
        <h1 className="text-xl font-semibold text-zinc-900">Discussion introuvable</h1>
        <p className="mt-3 text-sm text-zinc-600">
          Cette discussion n&apos;existe pas ou n&apos;est pas accessible avec ce compte.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-md bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-700"
        >
          Retour à l&apos;accueil
        </Link>
      </div>
    </main>
  );
}
