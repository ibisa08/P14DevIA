import type { Metadata } from "next";

// La page de login est un composant client : son titre est défini ici
export const metadata: Metadata = { title: "Connexion" };

export default function LoginLayout({ children }: LayoutProps<"/login">) {
  return children;
}
