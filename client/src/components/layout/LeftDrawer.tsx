import { motion } from 'framer-motion';
import { ReactNode } from 'react';

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
          bg-card/95 backdrop-blur
          overflow-hidden
        "
      >
        {/* CONTENT (hidden when collapsed) */}
        <div
          className={`
            h-full transition-opacity duration-200
            ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}
          `}
        >
          <div className="h-full overflow-y-auto px-2 py-2 space-y-4">
            {children}
          </div>
        </div>
      </motion.aside>

      {/* ================= TOGGLE (TRULY OUTSIDE) ================= */}
      <motion.button
        initial={false}
        animate={{
          left: open
            ? `calc(${width} + 7px)`     // fully outside drawer
            : `${collapsedWidth + 7}px`
        }}
        transition={{ type: 'spring', stiffness: 260, damping: 30 }}
        onClick={onToggle}
        className="
          absolute mt-1.5 z-40
          h-10 w-10 rounded-md
          bg-card hover:bg-muted
          border border-border/60
          flex items-center justify-center
          text-xs font-medium
          pointer-events-auto
        "
        aria-label="Toggle left drawer"
      >
        {open ? '◀' : '▶'}
      </motion.button>
    </>
  );
};

