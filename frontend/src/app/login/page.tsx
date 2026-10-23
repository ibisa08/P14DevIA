"use client";

import { CircleAlert, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { GuestOnly } from "@/components/AuthGuards";
import { Logo } from "@/components/Logo";
import { ApiError, ERROR_MESSAGES, login } from "@/lib/api";
import { setToken } from "@/lib/auth";

type LoginError = { message: string; status: number };

export default function LoginPage() {
  return (
    <main className="bg-login-grid flex min-h-screen items-center justify-center px-4 py-12">
      <GuestOnly loaderTone="light">
        <LoginCard />
      </GuestOnly>
    </main>
  );
}

function LoginCard() {
  const router = useRouter();
  const [error, setError] = useState<LoginError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Erreur imputable à la saisie (et non au réseau ou au serveur) : on marque les champs
  const fieldsInvalid = error !== null && (error.status === 401 || error.status === 422);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setError(null);
    setSubmitting(true);

    try {
      const { access_token } = await login(
        String(formData.get("email")),
        String(formData.get("password")),
      );
      if (!setToken(access_token)) {
        setError({ message: ERROR_MESSAGES.storageUnavailable, status: 0 });
        setSubmitting(false);
        return;
      }
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? { message: err.message, status: err.status }
          : { message: ERROR_MESSAGES.unexpected, status: 0 },
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-2xl bg-white px-6 py-10 shadow-2xl sm:px-8">
      <h1 className="text-center text-2xl">
        <Logo />
        <span className="sr-only"> : connexion</span>
      </h1>
      <p id="login-description" className="mt-4 text-center text-sm text-zinc-600">
        Connectez-vous pour accéder à votre assistant d&apos;actualités IA
      </p>

      <form
        onSubmit={handleSubmit}
        aria-describedby={error ? "login-description login-error" : "login-description"}
        className="mt-8 space-y-5"
      >
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-zinc-900">
            Adresse email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            placeholder="votre.email@exemple.com"
            aria-invalid={fieldsInvalid || undefined}
            aria-describedby={fieldsInvalid ? "login-error" : undefined}
            className="mt-2 block w-full rounded-md border border-zinc-500 bg-zinc-100 px-3 py-2 text-zinc-900 placeholder:text-zinc-600 aria-invalid:border-red-700"
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-zinc-900">
            Mot de passe
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            aria-invalid={fieldsInvalid || undefined}
            aria-describedby={fieldsInvalid ? "login-error" : undefined}
            className="mt-2 block w-full rounded-md border border-zinc-500 bg-zinc-100 px-3 py-2 text-zinc-900 aria-invalid:border-red-700"
          />
        </div>

        {/* Conteneur toujours présent : role="alert" annonce le message dès qu'il y est inséré */}
        <div id="login-error" role="alert">
          {error && (
            <p className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              {error.message}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-zinc-800 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-950 disabled:cursor-not-allowed disabled:opacity-75"
        >
          {submitting && (
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
          )}
          {submitting ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
