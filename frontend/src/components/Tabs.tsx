import { FileText, MessageCircle } from "lucide-react";
import Link from "next/link";

type TabsProps = { active: "chat" | "reviews" };

const TABS = [
  { id: "chat", label: "Chat", href: "/", Icon: MessageCircle },
  { id: "reviews", label: "Revue de presse", href: "/revues", Icon: FileText },
] as const;

/** Onglets « Chat » / « Revue de presse » (actif = violet plein, comme la maquette). */
export function Tabs({ active }: TabsProps) {
  return (
    <nav aria-label="Sections">
      <ul className="flex gap-2">
        {TABS.map(({ id, label, href, Icon }) => {
          const current = id === active;
          return (
            <li key={id}>
              <Link
                href={href}
                aria-current={current ? "page" : undefined}
                className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm transition-colors ${
                  current
                    ? "bg-violet-600 font-semibold text-white hover:bg-violet-700"
                    : "bg-zinc-100 text-zinc-800 hover:bg-zinc-200"
                }`}
              >
                <Icon aria-hidden="true" className="size-4" />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
