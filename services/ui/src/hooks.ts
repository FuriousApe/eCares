import { useCallback, useEffect, useRef, useState } from "react";
import type { Page } from "./types";

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useHashRoute(): [string, (to: string) => void] {
  const read = () => location.hash.replace(/^#/, "") || "/worklist";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const h = () => setRoute(read());
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  return [route, (to) => { location.hash = to; }];
}

/**
 * Cursor-paginated list. Refetching (filters changed, an action completed)
 * keeps the old rows on screen until the new page arrives, so the list never
 * flashes empty.
 */
export function usePaged<T>(fetchPage: (cursor?: string) => Promise<Page<T>>, deps: unknown[]) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;

  const reload = useCallback(() => {
    const id = ++seq.current;
    setError(null);
    fetchRef.current().then(
      (p) => {
        if (id !== seq.current) return;
        setItems(p.items);
        setCursor(p.next_cursor);
        setLoading(false);
      },
      (e: Error) => {
        if (id !== seq.current) return;
        setError(e.message);
        setLoading(false);
      },
    );
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(reload, deps);

  const loadMore = useCallback(() => {
    if (!cursor) return;
    const id = seq.current;
    setLoadingMore(true);
    fetchRef.current(cursor).then(
      (p) => {
        if (id !== seq.current) return;
        setItems((xs) => [...xs, ...p.items]);
        setCursor(p.next_cursor);
      },
      (e: Error) => setError(e.message),
    ).finally(() => setLoadingMore(false));
  }, [cursor]);

  return { items, loading, loadingMore, error, hasMore: cursor !== null, reload, loadMore };
}
