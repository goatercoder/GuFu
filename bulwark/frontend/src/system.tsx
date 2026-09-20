/** Which system (assessment scope) the UI is looking at. Persisted per browser. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSystems } from "./api/hooks";

const STORAGE_KEY = "bulwark.systemId";

interface SystemContextValue {
  systemId: number | null;
  setSystemId: (id: number) => void;
  /** True once the system list has loaded, whether or not it contains anything. */
  ready: boolean;
  /** How many systems exist. Zero means setup has not been done yet. */
  systemCount: number;
}

const SystemContext = createContext<SystemContextValue>({
  systemId: null, setSystemId: () => undefined, ready: false, systemCount: 0,
});

export const useSystem = () => useContext(SystemContext);

/** The selected system id, or throw: for pages that cannot render without one. */
export function useSystemId(): number {
  const { systemId } = useSystem();
  return systemId ?? 0;
}

function readStored(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

export function SystemProvider({ children }: { children: ReactNode }) {
  const { data: systems, isSuccess } = useSystems();
  const [systemId, setStateId] = useState<number | null>(readStored);

  const setSystemId = useCallback((id: number) => {
    setStateId(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      // A browser with storage disabled just loses the preference between visits.
    }
  }, []);

  useEffect(() => {
    if (!isSuccess || !systems) return;
    const known = systems.some((system) => system.id === systemId);
    if (!known) {
      const first = systems[0];
      if (first) setSystemId(first.id);
      else setStateId(null);
    }
  }, [isSuccess, systems, systemId, setSystemId]);

  // `ready` waits for the selection to settle as well as the fetch, so a first paint never
  // redirects to the setup wizard while a perfectly good system is about to be selected.
  const count = systems?.length ?? 0;
  const selectionSettled = count === 0
    || (systemId !== null && (systems ?? []).some((system) => system.id === systemId));

  const value = useMemo(
    () => ({ systemId, setSystemId, ready: isSuccess && selectionSettled, systemCount: count }),
    [systemId, setSystemId, isSuccess, selectionSettled, count],
  );
  return <SystemContext.Provider value={value}>{children}</SystemContext.Provider>;
}
