import { useState } from 'react';
import { Search, Filter, X, ChevronRight, TriangleAlert } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { Vessel } from '@/types';
import { vesselTypeData, anomalyTypeData } from '@/data/data';

/* ===================== TYPES ===================== */

interface SearchFilterPanelProps {
  vessels: Vessel[];
  onFilteredVessels: (vessels: Vessel[]) => void;
  onVesselSelect: (vessel: Vessel) => void;
  isDocked?: boolean;
}

const anomalyTypeOptions = [
  { value: 'all', label: 'All vessels' },
  ...Object.entries(anomalyTypeData).map(([key, data]) => ({
    value: key,
    label: data.label,
  })),
];

/* ===================== COMPONENT ===================== */

export const SearchFilterPanel = ({
  vessels,
  onFilteredVessels,
  onVesselSelect,
  isDocked = false,
}: SearchFilterPanelProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [anomalyTypeFilter, setAnomalyTypeFilter] = useState('all');
  const [isExpanded, setIsExpanded] = useState(false);

  /* ===================== FILTER LOGIC ===================== */

  const applyFilters = () => {
    let filtered = [...vessels];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(v =>
        v.name.toLowerCase().includes(q) ||
        v.mmsi.includes(q) ||
        (v.imo || '').toLowerCase().includes(q) ||
        (v.callSign || '').toLowerCase().includes(q)
      );
    }

    if (anomalyTypeFilter !== 'all') {
      filtered = filtered.filter(v => v.anomaly.type === anomalyTypeFilter);
    }

    onFilteredVessels(filtered);
  };

  const resetFilters = () => {
    setSearchQuery('');
    setAnomalyTypeFilter('all');
    onFilteredVessels(vessels);
  };

  const hasActiveFilters =
    searchQuery.trim() ||
    anomalyTypeFilter !== 'all';

  /* ===================== QUICK SEARCH ===================== */

  const searchResults = searchQuery.trim()
    ? vessels
      .filter(v =>
        v.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        v.mmsi.includes(searchQuery) ||
        (v.imo || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
      .slice(0, 5)
    : [];

  /* ===================== RENDER ===================== */

  return (
    <div className={cn(
      "overflow-hidden bg-card border border-border shadow-xl w-[360px] max-w-[calc(100vw-32px)] rounded-xl",
      isDocked && "w-full bg-transparent border-none shadow-none"
    )}>

      {/* SEARCH AREA */}
      <div className={cn(
        "p-[10px] space-y-[10px]",
        !isDocked && "border-b border-border bg-muted/5"
      )}>
        <div className="relative group flex items-center">
          <div className="relative flex-1">
            <div className="flex items-center h-12 rounded-xl border border-border bg-background/50 px-3 gap-2 focus-within:ring-2 focus-within:ring-primary/20 mr-[10px]">
              <Search
                className={cn(
                  "h-5 w-5 transition-colors",
                  searchQuery ? "text-primary animate-pulse-subtle" : "text-muted-foreground"
                )}
              />

              <Input
                placeholder="Search vessels or MMSI..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="flex-1 !border-0 !bg-transparent !shadow-none !p-0 focus-visible:!ring-0 focus-visible:!ring-offset-0"
              />

              {searchQuery && (
                <button
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  onClick={() => setSearchQuery('')}
                >
                  <X className="h-4 w-4" />
                </button>
              )}

            </div>
          </div>

          <Button
            variant="outline"
            size="icon"
            className={cn(
              "h-12 w-12 shrink-0 rounded-xl btn-standard border border-border/60",
              isExpanded ? "bg-primary/10 border-primary/30 text-primary" : "text-muted-foreground hover:border-border"
            )}
            onClick={() => setIsExpanded(v => !v)}
            title="Toggle Filters"
          >
            <Filter className="h-5 w-5" />
          </Button>
        </div>

        {/* SEARCH PREVIEW */}
        {searchResults.length > 0 && (
          <div className="space-y-[10px] py-[10px]">
            {searchResults.map(vessel => {
              const isAnomaly = vessel.anomaly.type === 'anomaly';
              const dotColor = isAnomaly ? 'rgb(234, 179, 8)' : 'rgb(59, 130, 246)';

              return (
                <button
                  key={vessel.id}
                  className="w-full text-left p-[10px] rounded-xl hover:bg-muted/50 flex justify-between items-center group border border-transparent hover:border-border"
                  onClick={() => {
                    onVesselSelect(vessel);
                    setSearchQuery('');
                  }}
                >
                  <div className="min-w-0">
                    <div className="text-sm font-bold truncate group-hover:text-primary transition-colors">{vessel.name}</div>
                    <div className="text-[11px] text-muted-foreground font-semibold flex items-center gap-[10px] mt-[10px]">
                      <div className="h-3 w-3 rounded-lg" style={{ backgroundColor: dotColor }} />
                      {vessel.mmsi || 'No MMSI'}
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground/30 group-hover:text-primary transition-transform group-hover:translate-x-1" />
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* QUICK ACTIONS / STATUS */}
      {isDocked && hasActiveFilters && !isExpanded && (
        <div className="px-[10px] py-[10px] flex items-center justify-between bg-primary/5 border-t border-border/20">
          <span className="text-[10px] font-bold text-primary uppercase tracking-wider">Active Filters</span>
          <button
            onClick={resetFilters}
            className="text-[10px] font-bold text-muted-foreground hover:text-primary transition-colors uppercase tracking-wider"
          >
            Clear All
          </button>
        </div>
      )}

      {/* FILTERS PANEL */}
      {isExpanded && (
        <div className={cn(
          "p-[10px] space-y-[10px] bg-card animate-in slide-in-from-top-2 duration-300",
          isDocked && "border-t border-border/40"
        )}>
          <div className="space-y-[10px]">
            <label className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60">Vessel Types</label>
            <Select value={anomalyTypeFilter} onValueChange={setAnomalyTypeFilter}>
              <SelectTrigger className="h-[42px] bg-background/50 border-border rounded-xl focus:ring-primary/20">
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent className="bg-card/95 backdrop-blur-lg border-border rounded-xl shadow-2xl">
                {anomalyTypeOptions.map(v => (
                  <SelectItem key={v.value} value={v.value} className="py-[10px] rounded-lg focus:bg-primary/10">
                    {v.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex gap-[10px]">
            <Button
              variant="outline"
              className="flex-1 h-[42px] btn-standard text-primary border-primary/40 bg-primary/5 hover:bg-primary/10 font-black uppercase tracking-widest text-[10px]"
              onClick={applyFilters}
            >
              Apply Changes
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
