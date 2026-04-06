import { useEffect } from 'react';

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
    useEffect(() => {
        const scrollY = isActive ? window.scrollY : state.scrollY;
        onStateChange(buildState(scrollY));
    }, [isActive, state.scrollY, onStateChange, buildState, ...syncDeps]);

    useEffect(() => {
        if (!isActive) {
            return;
        }
        restoreState();
    }, [isActive, restoreState]);
}
