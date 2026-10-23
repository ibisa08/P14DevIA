"use client";

import { CircleAlert, LogOut, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { useChats } from "@/components/ChatsProvider";
import { Logo } from "@/components/Logo";
import { PageLoader } from "@/components/PageLoader";
import { clearToken } from "@/lib/auth";
import { formatDate, formatTime } from "@/lib/format";

type SidebarProps = {
  /** Ouverte en mobile (sous md) ; sans effet sur grand écran où elle est toujours visible */
  open: boolean;
  onClose: (restoreFocus?: boolean) => void;
};

export function Sidebar({ open, onClose }: SidebarProps) {
  const router = useRouter();
  const params = useParams<{ id?: string }>();
  const activeChatId = params.id ? Number(params.id) : null;
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // En mobile, le focus passe dans la sidebar à son ouverture
  useEffect(() => {
    if (open) closeButtonRef.current?.focus();
  }, [open]);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <aside
      id="sidebar"
      aria-label="Barre latérale"
      className={`fixed inset-y-0 left-0 z-40 flex w-80 max-w-[85vw] flex-col border-r border-zinc-200 bg-zinc-50 transition-transform duration-200 motion-reduce:transition-none md:static md:z-auto md:max-w-none md:translate-x-0 ${
        // invisible (et non seulement décalée) : hors écran, ses liens ne doivent pas être atteignables au clavier
        open ? "translate-x-0" : "max-md:invisible max-md:-translate-x-full"
      }`}
    >
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 px-6 md:h-[88px]">
        <Link href="/" onClick={() => onClose()} className="rounded-sm text-lg">
          <Logo />
          <span className="sr-only"> : nouvelle discussion</span>
        </Link>
        <button
          ref={closeButtonRef}
          type="button"
          onClick={() => onClose(true)}
          className="rounded-md p-2 text-zinc-800 hover:bg-zinc-200 md:hidden"
        >
          <X aria-hidden="true" className="size-5" />
          <span className="sr-only">Fermer le menu</span>
        </button>
      </div>

      <nav aria-label="Discussions" className="min-h-0 flex-1 overflow-y-auto">
        <ChatList activeChatId={activeChatId} onNavigate={() => onClose()} />
      </nav>

      <div className="shrink-0 p-4">
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-sm text-zinc-900 hover:bg-zinc-200"
        >
          <LogOut aria-hidden="true" className="size-5" strokeWidth={1.5} />
          Se déconnecter
        </button>
      </div>
    </aside>
  );
}

function ChatList({ activeChatId, onNavigate }: { activeChatId: number | null; onNavigate: () => void }) {
  const { chats, error, reload } = useChats();

  if (error) {
    return (
      <div role="alert" className="space-y-2 p-6 text-sm">
        <p className="flex items-start gap-2 text-red-800">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {error}
        </p>
        <button type="button" onClick={reload} className="font-medium text-violet-700 underline underline-offset-2">
          Réessayer
        </button>
      </div>
    );
  }
  if (chats === null) {
    return (
      <div className="p-6">
        <PageLoader label="Chargement des discussions…" />
      </div>
    );
  }
  if (chats.length === 0) {
    return <p className="p-6 text-sm text-zinc-600">Aucune discussion pour l&apos;instant.</p>;
  }

  return (
    <ul>
      {chats.map((chat) => {
        const active = chat.id === activeChatId;
        return (
          <li key={chat.id} className="border-b border-zinc-200">
            <Link
              href={`/chats/${chat.id}`}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={`block border-l-4 py-4 pr-6 pl-5 -outline-offset-2 transition-colors ${
                active ? "border-violet-600 bg-violet-100" : "border-transparent hover:bg-zinc-100"
              }`}
            >
              <span className="block text-zinc-900">Discussion du</span>{" "}
              {/* Heure ajoutée à la maquette : distingue plusieurs discussions du même jour */}
              <time dateTime={chat.created_at} className="block text-xs text-zinc-600">
                {formatDate(chat.created_at)} à {formatTime(chat.created_at)}
              </time>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
