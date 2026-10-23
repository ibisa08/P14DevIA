import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";

/** Message d'erreur visible, avec une action optionnelle (ex. « Réessayer »). */
export function ErrorNotice({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
      <p className="flex items-start gap-2">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        {children}
      </p>
      {action}
    </div>
  );
}
