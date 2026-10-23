import { Bot } from "lucide-react";

/** Logo texte « NEWSFOUNDRY » + icône robot (décorative, masquée aux lecteurs d'écran). */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-medium tracking-wide text-violet-700 ${className}`}>
      NEWSFOUNDRY
      <Bot aria-hidden="true" className="size-[1.1em]" strokeWidth={2} />
    </span>
  );
}
