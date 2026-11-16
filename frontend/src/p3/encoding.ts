import { compareUtf8, sha256Hex } from "../replay/canon.ts";

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

export function requireInspection(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

export const decodeInspection = (bytes: ArrayBuffer): string => decoder.decode(bytes);
export const utf8 = (text: string): Uint8Array<ArrayBuffer> => encoder.encode(text);

/** The exporter sorts Unicode keys and permits only exact integers in its canonical JSON. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "string") {
    requireInspection(!/[\uD800-\uDFFF]/u.test(value), "Invalid Unicode in inspection JSON.");
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    requireInspection(Number.isSafeInteger(value), "Inspection JSON contains an inexact integer.");
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  requireInspection(typeof value === "object", "Invalid value in inspection JSON.");
  const fields = Object.entries(value).sort(([left], [right]) => {
    // UTF-16 and Unicode scalar order differ when one of the keys has a supplementary character.
    if (/[\uD800-\uDBFF]/.test(left) || /[\uD800-\uDBFF]/.test(right)) return compareUtf8(left, right);
    return left < right ? -1 : left > right ? 1 : 0;
  });
  return `{${fields.map(([key, item]) => `${canonicalJson(key)}:${canonicalJson(item)}`).join(",")}}`;
}

export async function sha256Bytes(bytes: ArrayBuffer | Uint8Array<ArrayBuffer>): Promise<string> {
  if (globalThis.crypto?.subtle === undefined) return sha256Hex(decoder.decode(bytes));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export const sameJson = (left: unknown, right: unknown): boolean => canonicalJson(left) === canonicalJson(right);
export const padNumber = (number: number, width = 6): string => String(number).padStart(width, "0");
export const deliveryId = (runId: string, actor: string, tick: number): string =>
  `${runId}:perception:${padNumber(tick, 10)}:${actor}`;
