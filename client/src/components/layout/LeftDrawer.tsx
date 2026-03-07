import { motion } from 'framer-motion';
import { ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LeftDrawerProps {
  open: boolean;
  width?: string;          // e.g. "30%"
  collapsedWidth?: number; // px
  onToggle: () => void;
  children: ReactNode;
}

export const LeftDrawer = ({
  open,
  width = '20%',
  collapsedWidth = 0,
  onToggle,
  children
}: LeftDrawerProps) => {
  return (
    <>
      {/* ================= LEFT DRAWER ================= */}
      <motion.aside
        initial={false}
        animate={{
          width: open ? width : collapsedWidth
        }}
        transition={{ type: 'spring', stiffness: 260, damping: 30 }}
        className="
          border-r border-border/60
          absolute top-0 left-0 z-30 h-full
          bg-card/95 backdrop-blur-md
          overflow-hidden
        "
      >
        {/* CONTENT (hidden when collapsed) */}
        <div
          className={cn(
            "h-full transition-opacity duration-300",
            open ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
        >
          <div className="h-full overflow-y-auto">
            {children}
          </div>
        </div>
      </motion.aside>

      {/* ================= TOGGLE BUTTON ================= */}
      <motion.button
        initial={false}
        animate={{
          left: open
            ? `calc(${width} + 10px)`
            : `${collapsedWidth + 10}px`,
          top: "10px"
        }}
        transition={{ type: 'spring', stiffness: 260, damping: 30 }}
        onClick={onToggle}
        className="
          absolute z-40
          h-[42px] w-[42px] rounded-xl
          bg-card hover:bg-muted
          border border-border
          flex items-center justify-center
          text-muted-foreground hover:text-foreground
          shadow-lg
          pointer-events-auto
        "
        aria-label="Toggle Navigation"
      >
        {open ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
      </motion.button>
    </>
  );
};

