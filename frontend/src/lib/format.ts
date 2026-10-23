// Formats français, affichés dans le fuseau du navigateur de l'utilisateur
const dateFormat = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" });
const timeFormat = new Intl.DateTimeFormat("fr-FR", { timeStyle: "short" });
const longDateTimeFormat = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** « 23/10/2026 » */
export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

/** « 14:32 » */
export function formatTime(iso: string): string {
  return timeFormat.format(new Date(iso));
}

/** « mardi 30 septembre 2025 à 09:00 » */
export function formatLongDateTime(iso: string): string {
  return longDateTimeFormat.format(new Date(iso));
}
