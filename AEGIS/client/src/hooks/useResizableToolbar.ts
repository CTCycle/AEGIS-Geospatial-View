import { useEffect, useState } from 'react';

const MIN_WIDTH = 280;
const MAX_WIDTH = 560;
const CANVAS_MIN_WIDTH = 320;

interface UseResizableToolbarOptions {
    initialWidth: number;
    onWidthChange?: (width: number) => void;
}

interface UseResizableToolbarResult {
    toolbarWidth: number;
    isResizing: boolean;
    setToolbarWidth: (width: number) => void;
    startResize: (onExpand?: () => void) => void;
}

const clampToolbarWidth = (value: number): number =>
    Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, value));

export const useResizableToolbar = ({
    initialWidth,
    onWidthChange,
}: UseResizableToolbarOptions): UseResizableToolbarResult => {
    const [toolbarWidth, setToolbarWidthInternal] = useState(clampToolbarWidth(initialWidth));
    const [isResizing, setIsResizing] = useState(false);

    useEffect(() => {
        setToolbarWidthInternal(clampToolbarWidth(initialWidth));
    }, [initialWidth]);

    useEffect(() => {
        onWidthChange?.(toolbarWidth);
    }, [onWidthChange, toolbarWidth]);

    useEffect(() => {
        if (!isResizing) {
            return;
        }

        const onMouseMove = (event: MouseEvent) => {
            const viewportWidth = window.innerWidth;
            const maxAllowedByViewport = viewportWidth - CANVAS_MIN_WIDTH;
            const clamped = clampToolbarWidth(Math.min(event.clientX, maxAllowedByViewport));
            setToolbarWidthInternal(clamped);
        };

        const onMouseUp = () => {
            setIsResizing(false);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };
    }, [isResizing]);

    const setToolbarWidth = (width: number) => {
        setToolbarWidthInternal(clampToolbarWidth(width));
    };

    const startResize = (onExpand?: () => void) => {
        onExpand?.();
        setIsResizing(true);
    };

    return {
        toolbarWidth,
        isResizing,
        setToolbarWidth,
        startResize,
    };
};
