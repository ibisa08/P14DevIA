"use client";

import { CircleAlert, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RequireAuth } from "@/components/AuthGuards";
import { Logo } from "@/components/Logo";
import { PageLoader } from "@/components/PageLoader";
import { ApiError, ERROR_MESSAGES, getMe, type User } from "@/lib/api";
import { clearToken } from "@/lib/auth";

// Accueil provisoire (étape 3) : sera remplacé par l'interface de chat
export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#eeedf6] px-4 py-12">
      <RequireAuth>
        <Welcome />
      </RequireAuth>
    </main>
  );
}

function Welcome() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Incrémenté par « Réessayer » pour relancer l'appel à /me
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Ignore une réponse arrivée après le démontage du composant
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) setUser(me);
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

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="w-full max-w-md rounded-2xl bg-white px-6 py-10 text-center shadow-lg sm:px-8">
      <p className="text-xl">
        <Logo />
      </p>
      <h1 className="mt-6 text-2xl font-semibold text-zinc-900">Bienvenue</h1>

      <div className="mt-4 flex min-h-12 items-center justify-center">
        {error ? (
          <div role="alert" className="w-full space-y-3">
            <p className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-left text-sm text-red-800">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              {error}
            </p>
            <button
              type="button"
              onClick={retry}
              className="text-sm font-medium text-violet-700 underline underline-offset-2 hover:text-violet-900"
            >
              Réessayer
            </button>
          </div>
        ) : user ? (
          <p className="text-zinc-700">
            Connecté en tant que <strong className="font-semibold text-zinc-900">{user.email}</strong>
          </p>
        ) : (
          <PageLoader label="Chargement du profil…" />
        )}
      </div>

      <button
        type="button"
        onClick={logout}
        className="mt-8 inline-flex items-center gap-2 rounded-md bg-zinc-800 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-950"
      >
        <LogOut aria-hidden="true" className="size-4" />
        Se déconnecter
      </button>
    </div>
  );
}
