"use client";

import { ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface ExplorerProps {
    open: boolean;
    width?: string;
    collapsedWidth?: number;
    onToggle: () => void;
    children: ReactNode;
}

export const Explorer = ({
    open,
    width = "20%",
    collapsedWidth = 0,
    onToggle,
    children,
}: ExplorerProps) => {
    return (
        <>
            <aside
                className={cn(
                    "border-r border-border/60 absolute top-0 left-0 z-100 h-[100dvh] bg-card/95 backdrop-blur-md overflow-hidden",
                    open ? "block" : "hidden"
                )}
                style={{ width }}
            >
                <div className="h-full">
                    <div className="h-full overflow-hidden">
                        {children}
                    </div>
                </div>
            </aside>

            {!open && (
                <button
                    onClick={onToggle}
                    className="absolute z-101 flex items-center justify-center bg-background border-border border-r border-b hover:bg-muted transition-all h-20 w-8 rounded-none rounded-br-md left-0 top-0 active:translate-y-px duration-200"
                    aria-label="Open Navigation"
                >
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </button>
            )}
        </>
    );
};
