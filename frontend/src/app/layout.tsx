import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Police proche de celle des maquettes
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "NewsFoundry", template: "%s – NewsFoundry" },
  description: "Assistant de revue de presse par IA pour pigistes",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
