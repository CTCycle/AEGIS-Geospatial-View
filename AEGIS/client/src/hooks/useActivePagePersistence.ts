import { useEffect, useRef } from 'react';

interface UseActivePagePersistenceOptions<TState extends { scrollY: number }> {
    isActive: boolean;
    state: TState;
    onStateChange: (state: TState) => void;
    buildState: (scrollY: number) => TState;
    restoreState: () => void;
    syncDeps: readonly unknown[];
}

export function useActivePagePersistence<TState extends { scrollY: number }>({
    isActive,
    state,
    onStateChange,
    buildState,
    restoreState,
    syncDeps,
}: UseActivePagePersistenceOptions<TState>): void {
    const onStateChangeRef = useRef(onStateChange);
    const buildStateRef = useRef(buildState);
    const restoreStateRef = useRef(restoreState);

    useEffect(() => {
        onStateChangeRef.current = onStateChange;
    }, [onStateChange]);

    useEffect(() => {
        buildStateRef.current = buildState;
    }, [buildState]);

    useEffect(() => {
        restoreStateRef.current = restoreState;
    }, [restoreState]);

    useEffect(() => {
        const scrollY = isActive ? window.scrollY : state.scrollY;
        onStateChangeRef.current(buildStateRef.current(scrollY));
    }, [isActive, state.scrollY, ...syncDeps]);

    useEffect(() => {
        if (!isActive) {
            return;
        }
        restoreStateRef.current();
    }, [isActive]);
}
