export const number = (value: number) => new Intl.NumberFormat("en-IN").format(value);
export const level = (value: number) => `${value.toFixed(1)}m`;
export const distance = (value: number) => `${value.toFixed(1)} KM`;
export const time = (value: string | null, timezone: string) => value
  ? new Intl.DateTimeFormat("en-GB", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(value))
  : "—";
export const date = (value: string, timezone: string) => new Intl.DateTimeFormat("en-GB", {
  timeZone: timezone, day: "2-digit", month: "short", year: "numeric",
}).format(new Date(value)).toUpperCase();

export function minutesUntil(deadline: string, replayAt: string): number {
  return Math.max(0, Math.ceil((Date.parse(deadline) - Date.parse(replayAt)) / 60000));
}

export function remaining(deadline: string | null, replayAt: string): string {
  if (!deadline) return "NO DEPARTURE REQUIRED";
  if (Date.parse(deadline) <= Date.parse(replayAt)) return "DEADLINE REACHED";
  return `${minutesUntil(deadline, replayAt)} MIN REMAINING`;
}
