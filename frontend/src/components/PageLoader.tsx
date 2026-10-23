import { LoaderCircle } from "lucide-react";

export function PageLoader({ label = "Chargement…", tone = "dark" }: { label?: string; tone?: "dark" | "light" }) {
  return (
    <p role="status" className={`flex items-center gap-2 text-sm ${tone === "light" ? "text-zinc-200" : "text-zinc-700"}`}>
      <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
      {label}
    </p>
  );
}
