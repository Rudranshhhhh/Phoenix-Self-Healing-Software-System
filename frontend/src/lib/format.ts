export function since(value: string | number | Date | null | undefined): string {
  if (!value) return "never";
  const date = value instanceof Date ? value : new Date(value);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (isNaN(diffMs) || diffMs < 0) return "just now";

  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;

  const diffDay = Math.floor(diffHour / 24);
  if (diffDay === 1) return "yesterday";
  if (diffDay < 30) return `${diffDay}d ago`;

  const diffMonth = Math.floor(diffDay / 30);
  if (diffMonth < 12) return `${diffMonth}mo ago`;

  return `${Math.floor(diffDay / 365)}y ago`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null || isNaN(seconds)) return "0s";
  const sec = Math.floor(seconds);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return remSec > 0 ? `${min}m ${remSec}s` : `${min}m`;
  const hour = Math.floor(min / 60);
  const remMin = min % 60;
  if (hour < 24) return remMin > 0 ? `${hour}h ${remMin}m` : `${hour}h`;
  const days = Math.floor(hour / 24);
  const remHour = hour % 24;
  return remHour > 0 ? `${days}d ${remHour}h` : `${days}d`;
}

export function clock(value: string | number | Date | null | undefined): string {
  if (!value) return "--:--:--";
  const date = value instanceof Date ? value : new Date(value);
  if (isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
