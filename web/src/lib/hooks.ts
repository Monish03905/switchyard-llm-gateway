import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "./api";

export function useFetch<T>(path: string | null, pollMs = 0, admin = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [nonce, setNonce] = useState(0);
  const dataRef = useRef<T | null>(null);
  dataRef.current = data;

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setLoading(dataRef.current === null);

    const load = async () => {
      try {
        const payload = await api.get<T>(path, { admin });
        if (!active) return;
        setData(payload);
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(errorMessage(err));
      } finally {
        if (!active) return;
        setLoading(false);
        if (pollMs > 0) timer = setTimeout(load, pollMs);
      }
    };

    load();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [path, pollMs, admin, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, reload, setData };
}

export function useTicker(ms = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}

export function useDeferredValueCompat<T>(value: T, delay = 250): T {
  const [deferred, setDeferred] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDeferred(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return deferred;
}
