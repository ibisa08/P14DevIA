"use client";

import { LoaderCircle, Send } from "lucide-react";
import { useId, type FormEvent, type KeyboardEvent, type Ref } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { MESSAGE_MAX_LENGTH } from "@/lib/api";

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  /** Reçoit le message sans espaces superflus ; jamais appelé si vide ou pendant un envoi */
  onSubmit: (content: string) => void;
  busy: boolean;
  /** Envoi impossible pour l'instant (ex. discussion pas encore chargée), sans indicateur */
  disabled?: boolean;
  /** Erreur affichée au-dessus de la saisie (le texte saisi est conservé) */
  error?: string | null;
  textareaRef?: Ref<HTMLTextAreaElement>;
};

/** Zone de saisie en bas de page : Entrée envoie, Maj+Entrée va à la ligne. */
export function Composer({ value, onChange, onSubmit, busy, disabled = false, error, textareaRef }: ComposerProps) {
  const hintId = useId();
  const canSend = value.trim().length > 0 && !busy && !disabled;

  function submit() {
    if (canSend) onSubmit(value.trim());
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // isComposing : Entrée valide une saisie IME (accents composés, japonais...) sans envoyer
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="shrink-0 border-t border-zinc-200 bg-zinc-50 px-4 py-4 sm:px-8">
      {/* Conteneur toujours présent : role="alert" annonce le message dès qu'il y est inséré */}
      <div role="alert" className="mx-auto max-w-5xl empty:hidden">
        {error && <div className="mb-3"><ErrorNotice>{error}</ErrorNotice></div>}
      </div>
      <form onSubmit={handleSubmit} className="mx-auto flex max-w-5xl items-start gap-2 sm:gap-3">
        <label htmlFor="composer" className="sr-only">
          Votre message
        </label>
        <textarea
          id="composer"
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          maxLength={MESSAGE_MAX_LENGTH}
          placeholder="Tapez votre message ici..."
          aria-describedby={hintId}
          className="min-h-15 flex-1 resize-none rounded-md border border-zinc-300 bg-zinc-100 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-600 focus-visible:border-violet-600"
        />
        <p id={hintId} className="sr-only">
          Entrée pour envoyer, Maj+Entrée pour aller à la ligne.
        </p>
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Envoyer"
          aria-busy={busy}
          className="flex size-10 shrink-0 items-center justify-center rounded-md bg-violet-600 text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
        >
          {busy ? (
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
          ) : (
            <Send aria-hidden="true" className="size-4" />
          )}
        </button>
      </form>
    </div>
  );
}
