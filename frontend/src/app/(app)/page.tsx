"use client";

import { Bot } from "lucide-react";
import { useRef, useState } from "react";

import { Composer } from "@/components/Composer";
import { Tabs } from "@/components/Tabs";
import { useStartChat } from "@/hooks/useStartChat";

const EXAMPLES = [
  "Quelles sont les dernières nouvelles en politique ?",
  "Génère une revue de presse sur la technologie",
  "Résume l'actualité économique de la semaine",
];

// Accueil : présentation de l'assistant ; le premier envoi crée une discussion
export default function HomePage() {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { startChat, starting, error } = useStartChat();

  function fillWithExample(example: string) {
    setDraft(example);
    textareaRef.current?.focus();
  }

  return (
    <>
      <header className="flex h-[88px] shrink-0 items-center border-b border-zinc-200 bg-zinc-50 px-4 sm:px-5">
        <Tabs active="chat" />
      </header>

      <main className="flex min-h-0 flex-1 overflow-y-auto bg-canvas px-4 py-8">
        <section
          aria-labelledby="assistant-title"
          className="m-auto w-full max-w-[543px] rounded-xl border border-zinc-200 bg-white px-6 py-12 text-center sm:px-16"
        >
          <Bot aria-hidden="true" className="mx-auto size-20 text-violet-600" strokeWidth={1.75} />
          <h1 id="assistant-title" className="mt-4 text-3xl text-violet-700">
            Assistant Revue de Presse IA
          </h1>
          <p className="mt-10 text-zinc-600">
            Posez-moi des questions sur l&apos;actualité récente ou demandez-moi de générer une revue de
            presse sur un sujet spécifique.
          </p>

          <h2 className="mt-10 text-sm font-semibold text-zinc-600">Exemples :</h2>
          <ul className="mt-2 space-y-1 text-sm text-zinc-600">
            {EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  onClick={() => fillWithExample(example)}
                  className="rounded-sm px-1 py-0.5 hover:text-violet-700 hover:underline"
                >
                  <span aria-hidden="true">• </span>
                  <span className="sr-only">Utiliser l&apos;exemple : </span>
                  &quot;{example}&quot;
                </button>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <Composer
        value={draft}
        onChange={setDraft}
        onSubmit={startChat}
        busy={starting}
        error={error}
        textareaRef={textareaRef}
      />
    </>
  );
}
