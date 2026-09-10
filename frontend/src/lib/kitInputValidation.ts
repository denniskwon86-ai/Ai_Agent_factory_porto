/** Independent source control total. Never default it to the uploaded snapshot's own count. */
export function sourceRowCount(value: string): number | null {
  if (!/^[0-9]+$/.test(value.trim())) return null;
  const count = Number(value.trim());
  return Number.isSafeInteger(count) && count > 0 ? count : null;
}
