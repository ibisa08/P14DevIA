"use client";

import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { RequireAuth } from "@/components/AuthGuards";
import { ChatsProvider } from "@/components/ChatsProvider";
import { Logo } from "@/components/Logo";
import { Sidebar } from "@/components/Sidebar";

/** Layout authentifié : sidebar des discussions + zone principale. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <ChatsProvider>
        <Shell>{children}</Shell>
      </ChatsProvider>
    </RequireAuth>
  );
}

function Shell({ children }: { children: ReactNode }) {
  // Sidebar repliable sous 768 px (md) ; toujours visible au-delà
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  const closeSidebar = useCallback((restoreFocus = false) => {
    setSidebarOpen(false);
    if (restoreFocus) menuButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeSidebar(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [sidebarOpen, closeSidebar]);

  return (
    <div className="flex h-dvh overflow-hidden bg-zinc-50">
      <Sidebar open={sidebarOpen} onClose={closeSidebar} />

      {/* Voile cliquable derrière la sidebar ouverte en mobile */}
      {sidebarOpen && (
        <div
          aria-hidden="true"
          onClick={() => closeSidebar(true)}
          className="fixed inset-0 z-30 bg-zinc-950/40 md:hidden"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-zinc-200 bg-zinc-50 px-4 md:hidden">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-expanded={sidebarOpen}
            aria-controls="sidebar"
            className="rounded-md p-2 text-zinc-800 hover:bg-zinc-200"
          >
            <Menu aria-hidden="true" className="size-5" />
            <span className="sr-only">Ouvrir le menu des discussions</span>
          </button>
          <Logo />
        </div>
        {children}
      </div>
    </div>
  );
}
