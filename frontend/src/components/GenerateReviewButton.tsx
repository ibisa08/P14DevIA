"use client";

import { FileText, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState, type FormEvent, type MouseEvent, type SyntheticEvent } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { ApiError, ERROR_MESSAGES, TOPIC_MAX_LENGTH, generateReview } from "@/lib/api";

type GenerateReviewButtonProps = { chatId: number; disabled: boolean };

/**
 * Bouton « Générer une revue de presse » + modale de saisie du sujet.
 *
 * <dialog> natif ouvert avec showModal() : le reste de la page devient inerte (focus piégé),
 * Échap ferme la modale et le focus revient au bouton à la fermeture.
 */
export function GenerateReviewButton({ chatId, disabled }: GenerateReviewButtonProps) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [topic, setTopic] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const errorId = useId();

  function open() {
    setError(null);
    dialogRef.current?.showModal();
  }

  function close() {
    if (!generating) dialogRef.current?.close();
  }

  // Échap déclenche « cancel » : bloqué pendant la génération pour ne pas perdre le résultat
  function handleCancel(event: SyntheticEvent<HTMLDialogElement>) {
    if (generating) event.preventDefault();
  }

  // Clic sur le voile (hors du contenu) : fermeture, comme Échap
  function handleBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === dialogRef.current) close();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedTopic = topic.trim();
    if (!trimmedTopic || generating) return;

    setGenerating(true);
    setError(null);
    try {
      await generateReview(chatId, trimmedTopic);
      router.push("/revues");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : ERROR_MESSAGES.unexpected);
      setGenerating(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        disabled={disabled}
        className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60 sm:px-6 sm:text-base"
      >
        <FileText aria-hidden="true" className="size-4 shrink-0" />
        <span>
          Générer <span className="max-sm:sr-only">une revue de presse</span>
        </span>
      </button>

      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onCancel={handleCancel}
        onClick={handleBackdropClick}
        className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl bg-white p-0 text-zinc-900 shadow-2xl backdrop:bg-zinc-950/50"
      >
        <form onSubmit={handleSubmit} className="space-y-5 p-6 sm:p-8">
          <div>
            <h2 id={titleId} className="text-xl font-semibold">
              Générer une revue de presse
            </h2>
            <p id={descriptionId} className="mt-2 text-sm text-zinc-600">
              La revue est rédigée à partir de cette discussion, puis enregistrée dans vos revues de presse.
            </p>
          </div>

          <div>
            <label htmlFor="review-topic" className="block text-sm font-medium">
              Sujet de la revue
            </label>
            <input
              id="review-topic"
              type="text"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              required
              autoFocus
              maxLength={TOPIC_MAX_LENGTH}
              placeholder="Ex. : l'IA dans la santé et l'éducation"
              // readOnly plutôt que disabled : le champ garde le focus pendant la génération
              readOnly={generating}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              className="mt-2 block w-full rounded-md border border-zinc-500 bg-zinc-100 px-3 py-2 placeholder:text-zinc-600 read-only:opacity-60"
            />
          </div>

          <div id={errorId} role="alert">
            {error && <ErrorNotice>{error}</ErrorNotice>}
          </div>

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={close}
              disabled={generating}
              className="rounded-md border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-800 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={generating || !topic.trim()}
              aria-busy={generating}
              className="flex items-center justify-center gap-2 rounded-md bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {generating && (
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
              )}
              {generating ? "Génération en cours…" : "Générer"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
