import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";

// Groupe de routes (app) : toutes les pages authentifiées partagent la sidebar
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
