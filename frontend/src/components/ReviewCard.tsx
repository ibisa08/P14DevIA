"use client";

import { Calendar, Check, ExternalLink } from "lucide-react";
import { useEffect, useId, useState } from "react";

import type { PressReview } from "@/lib/api";
import { formatLongDateTime } from "@/lib/format";

type CopyStatus = "idle" | "copied" | "failed";

/** Revue en texte brut, prête à coller dans un mail ou un traitement de texte. */
function reviewToText(review: PressReview): string {
  const { content } = review;
  const articles = content.articles.map((article) => {
    const heading = article.source ? `• ${article.title} (${article.source})` : `• ${article.title}`;
    return [heading, `  ${article.summary}`, article.url ? `  ${article.url}` : null]
      .filter(Boolean)
      .join("\n");
  });
  return [
    content.title,
    formatLongDateTime(review.created_at),
    `Sujet : ${review.topic}`,
    "",
    "Synthèse générale",
    content.summary,
    ...(articles.length ? ["", "Articles", ...articles] : []),
  ].join("\n");
}

export function ReviewCard({ review }: { review: PressReview }) {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const titleId = useId();
  const { content } = review;

  // Le bouton revient à « Copier » après quelques secondes
  useEffect(() => {
    if (copyStatus === "idle") return;
    const timer = window.setTimeout(() => setCopyStatus("idle"), 3000);
    return () => window.clearTimeout(timer);
  }, [copyStatus]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(reviewToText(review));
      setCopyStatus("copied");
    } catch {
      // Presse-papiers refusé par le navigateur (permission, contexte non sécurisé)
      setCopyStatus("failed");
    }
  }

  return (
    <article aria-labelledby={titleId} className="rounded-xl bg-white px-6 py-8 sm:px-10 sm:py-10">
      <div className="flex flex-col-reverse gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id={titleId} className="text-zinc-950 break-words">
            {review.title}
          </h2>
          <p className="mt-1 flex items-center gap-2 text-zinc-600">
            <Calendar aria-hidden="true" className="size-4 shrink-0" strokeWidth={1.5} />
            <time dateTime={review.created_at}>{formatLongDateTime(review.created_at)}</time>
          </p>
          <p className="mt-1 text-sm text-zinc-600">Sujet : {review.topic}</p>
        </div>

        <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
          <button
            type="button"
            onClick={copy}
            className="flex items-center gap-2 rounded-md bg-zinc-800 px-6 py-2.5 text-sm text-white transition-colors hover:bg-zinc-950"
          >
            {copyStatus === "copied" && <Check aria-hidden="true" className="size-4" />}
            {copyStatus === "copied" ? "Copié" : "Copier"}
            <span className="sr-only"> la revue « {review.title} »</span>
          </button>
          {/* Région toujours présente : le résultat de la copie est annoncé aux lecteurs d'écran */}
          <p aria-live="polite" className="text-xs text-zinc-600">
            {copyStatus === "copied" && "Revue copiée dans le presse-papiers."}
            {copyStatus === "failed" && (
              <span className="text-red-800">Copie impossible : le navigateur a refusé l&apos;accès au presse-papiers.</span>
            )}
          </p>
        </div>
      </div>

      <div className="mt-6 space-y-6 text-sm text-zinc-900 sm:pl-6">
        <section aria-label="Synthèse générale">
          <h3 className="font-semibold">Synthèse générale</h3>
          <p className="mt-2 whitespace-pre-line">{content.summary}</p>
        </section>

        {content.articles.length > 0 && (
          <section aria-label="Articles">
            <h3 className="font-semibold">Articles</h3>
            <ul className="mt-2 space-y-4">
              {content.articles.map((article, index) => (
                <li key={index} className="flex gap-2">
                  <span aria-hidden="true">•</span>
                  <div className="min-w-0">
                    <p>
                      <strong className="font-semibold">{article.title}</strong>
                      {article.source && <span className="text-zinc-600"> — {article.source}</span>}
                    </p>
                    <p className="mt-1 whitespace-pre-line">{article.summary}</p>
                    {article.url && (
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-flex items-center gap-1 font-medium text-violet-800 underline underline-offset-2"
                      >
                        Lire l&apos;article
                        <ExternalLink aria-hidden="true" className="size-3.5" />
                        <span className="sr-only"> « {article.title} » (nouvel onglet)</span>
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </article>
  );
}
