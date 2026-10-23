"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { PageLoader } from "@/components/PageLoader";
import { useAuthToken } from "@/lib/auth";

type GuardProps = { children: ReactNode; loaderTone?: "dark" | "light" };

/** Affiche `children` seulement si un token est présent, sinon redirige vers /login. */
export function RequireAuth({ children, loaderTone }: GuardProps) {
  const token = useAuthToken();
  const router = useRouter();

  useEffect(() => {
    if (token === null) router.replace("/login");
  }, [token, router]);

  // undefined (pas encore lu) ou null (redirection en cours) : jamais de contenu protégé
  if (!token) return <PageLoader tone={loaderTone} />;
  return children;
}

/** Pages publiques (login) : un utilisateur déjà connecté est renvoyé vers l'accueil. */
export function GuestOnly({ children, loaderTone }: GuardProps) {
  const token = useAuthToken();
  const router = useRouter();

  useEffect(() => {
    if (token) router.replace("/");
  }, [token, router]);

  if (token !== null) return <PageLoader tone={loaderTone} />;
  return children;
}
