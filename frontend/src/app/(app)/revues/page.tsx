"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Composer } from "@/components/Composer";
import { ErrorNotice } from "@/components/ErrorNotice";
import { PageLoader } from "@/components/PageLoader";
import { ReviewCard } from "@/components/ReviewCard";
import { Tabs } from "@/components/Tabs";
import { useStartChat } from "@/hooks/useStartChat";
import { ApiError, ERROR_MESSAGES, listReviews, type PressReview } from "@/lib/api";

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<PressReview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Incrémenté par « Réessayer » pour relancer le chargement
  const [attempt, setAttempt] = useState(0);
  // La zone de saisie de la maquette démarre une nouvelle discussion, comme sur l'accueil
  const [draft, setDraft] = useState("");
  const { startChat, starting, error: startError } = useStartChat();

  useEffect(() => {
    let cancelled = false;
    listReviews()
      .then((result) => {
        if (!cancelled) setReviews(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : ERROR_MESSAGES.unexpected);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  function retry() {
    setError(null);
    setAttempt((value) => value + 1);
  }

  return (
    <>
      <header className="flex h-[88px] shrink-0 items-center border-b border-zinc-200 bg-zinc-50 px-4 sm:px-5">
        <Tabs active="reviews" />
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto bg-canvas px-4 py-8 sm:px-8 sm:py-14">
        <div className="mx-auto max-w-[925px]">
          <h1 className="text-2xl font-medium text-zinc-950">Revues de Presse</h1>
          <p className="mt-1 text-zinc-600">Consultez et gérez vos revues de presse générées par l&apos;IA</p>

          <div className="mt-4">
            {error ? (
              <div role="alert">
                <ErrorNotice
                  action={
                    <button type="button" onClick={retry} className="font-medium underline underline-offset-2">
                      Réessayer
                    </button>
                  }
                >
                  {error}
                </ErrorNotice>
              </div>
            ) : reviews === null ? (
              <PageLoader label="Chargement des revues de presse…" />
            ) : reviews.length === 0 ? (
              <div className="rounded-xl bg-white px-6 py-12 text-center">
                <p className="text-zinc-700">Aucune revue pour l&apos;instant.</p>
                <p className="mt-2 text-sm text-zinc-600">
                  Ouvrez une discussion puis utilisez « Générer une revue de presse ».
                </p>
                <Link
                  href="/"
                  className="mt-6 inline-block rounded-md bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-700"
                >
                  Aller au chat
                </Link>
              </div>
            ) : (
              <ul className="space-y-3">
                {reviews.map((review) => (
                  <li key={review.id}>
                    <ReviewCard review={review} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </main>

      <Composer value={draft} onChange={setDraft} onSubmit={startChat} busy={starting} error={startError} />
    </>
  );
}
